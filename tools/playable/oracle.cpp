// Ghost oracle: replays a recorded pad input file and logs the game state.
//
// Linked only into the playable build (tools/build_playable.py --oracle),
// which compiles everything with -DSMS_ORACLE. The matching sources carry
// three hooks behind that define, so the normal (matching) build is byte for
// byte unchanged:
//   JUTGamePad::read        -> SMSOracle_onPadRead  (after PADRead+PADClamp)
//   TMarDirector::changeState -> SMSOracle_onStateChange
//   TMarDirector::direct    -> SMSOracle_onTick     (end of every sim tick)
//
// Input: files/ghost_input.bin on the disc / extracted game folder, read with
// the game's own DVD API when the director enters STATE_UNK1 (the stage
// intro). That tick is tick 0 of the log. Layout (big-endian):
//
//   0x00 char[4] "SGIN"
//   0x04 u16     version = 1
//   0x06 u16     flags (bit 0: rng seed present)
//   0x08 u32     record count
//   0x0C u32     first logged tick (relative to the arming tick)
//   0x10 u32     last logged tick
//   0x14 u32     rng seed (if flags bit 0): applied with srand() at arming
//   0x18 u32     tick the first record's frame ends on
//   0x1C u32     reserved
//   0x20 records, 12 bytes each, one per frame (one PADRead):
//        u16 buttons, s8 stickX, s8 stickY, s8 substickX, s8 substickY,
//        u8 triggerL, u8 triggerR, u8 analogA, u8 analogB, u16 reserved
//
// Record n is the PADStatus of the frame whose last sim tick is
// firstRecordTick + n * ticksPerFrame. Before the first record and after the
// last one the pad reads neutral. Port 0 only.
//
// Output: OSReport lines (Dolphin: enable the OSReport log). Floats are
// printed as their 32-bit hex pattern, so nothing is lost to formatting.
//
//   O arm tick=<n> frame=<n> tpf=<n> recs=<n> first=<n> log=<a>-<b> seed=<x>
//   O state tick=<n> frame=<n> state=<n>     every director state change
//   I frame=<n> tick=<n> rec=<n|-> b=<hex> x=<n> y=<n> cx=<n> cy=<n> l=<n> r=<n>
//                                            every pad read after arming
//   T <tick> <frame> <state> <mode> <cue>    one per sim tick in the log range
//     st=<status> p=<x> <y> <z> v=<x> <y> <z> fv=<f> yaw=<hex> w=<n>
//     cp=<x> <y> <z> ct=<x> <y> <z> rng=<hex>
//
// tick is the director's tick counter minus its value at arming, frame is the
// number of pad reads since arming, cue is 1 when CUE_MOVE ran this tick.

#include <System/MarDirector.hpp>
#include <System/Application.hpp>
#include <System/MarioGamePad.hpp>
#include <Player/Mario.hpp>
#include <Player/WaterGun.hpp>
#include <Camera/Camera.hpp>
#include <JSystem/JKernel/JKRHeap.hpp>
#include <dolphin/dvd.h>
#include <dolphin/os.h>
#include <dolphin/pad.h>
#include <stdlib.h>

// C++ linkage, declared the same way at the hook sites
void SMSOracle_onPadRead(PADStatus* status);
void SMSOracle_onStateChange(u8 state);
void SMSOracle_onTick(u32 tickCount, u32 moveTickCount, u32 cue);


namespace {

struct Record {
	u16 buttons;
	s8 stickX;
	s8 stickY;
	s8 substickX;
	s8 substickY;
	u8 triggerL;
	u8 triggerR;
	u8 analogA;
	u8 analogB;
	u16 reserved;
};

struct Header {
	char magic[4];
	u16 version;
	u16 flags;
	u32 recordCount;
	u32 firstLogTick;
	u32 lastLogTick;
	u32 rngSeed;
	u32 firstRecordTick;
	u32 reserved;
};

bool sArmed      = false;
bool sLoaded     = false;
bool sTriedLoad  = false;
u32 sArmTick     = 0; // mTickCount at arming
u32 sFrame       = 0; // pad reads since arming
u32 sLastTick    = 0; // ticks since arming, as of the last sim tick
u32 sTicksPerFrame = 4;
Header sHeader;
Record* sRecords = 0;

inline u32 fbits(f32 f) { return *(u32*)&f; }

bool load()
{
	sTriedLoad = true;
	DVDFileInfo info;
	if (!DVDOpen("/ghost_input.bin", &info)) {
		OSReport("O error: files/ghost_input.bin not found\n");
		return false;
	}
	u32 len = (info.length + 31) & ~31;
	u8* buf = (u8*)JKRHeap::alloc(len, 32, JKRHeap::getSystemHeap());
	if (!buf) {
		OSReport("O error: no memory for ghost_input.bin (%u bytes)\n", len);
		DVDClose(&info);
		return false;
	}
	s32 got = DVDReadPrio(&info, buf, len, 0, 2);
	DVDClose(&info);
	if (got < (s32)sizeof(Header)) {
		OSReport("O error: ghost_input.bin read failed (%d)\n", got);
		return false;
	}
	sHeader = *(Header*)buf;
	if (sHeader.magic[0] != 'S' || sHeader.magic[1] != 'G'
	    || sHeader.magic[2] != 'I' || sHeader.magic[3] != 'N'
	    || sHeader.version != 1) {
		OSReport("O error: ghost_input.bin bad magic/version\n");
		return false;
	}
	u32 need = sizeof(Header) + sHeader.recordCount * sizeof(Record);
	if (info.length < need) {
		OSReport("O error: ghost_input.bin truncated (%u < %u)\n", info.length,
		         need);
		return false;
	}
	sRecords = (Record*)(buf + sizeof(Header));
	return true;
}

void arm()
{
	if (!sTriedLoad)
		sLoaded = load();
	sArmed    = true;
	sArmTick  = gpMarDirector->mTickCount;
	sFrame    = 0;
	sLastTick = 0;
	sTicksPerFrame = (u32)(600 / (int)SMSGetVSyncTimesPerSec()) / 5;
	if (sLoaded && (sHeader.flags & 1))
		srand(sHeader.rngSeed);
	OSReport("O arm tick=0 frame=0 tpf=%u recs=%u first=%u log=%u-%u seed=%08x "
	         "loaded=%d\n",
	         sTicksPerFrame, sLoaded ? sHeader.recordCount : 0,
	         sLoaded ? sHeader.firstRecordTick : 0,
	         sLoaded ? sHeader.firstLogTick : 0,
	         sLoaded ? sHeader.lastLogTick : 0,
	         (sLoaded && (sHeader.flags & 1)) ? sHeader.rngSeed : 0,
	         sLoaded ? 1 : 0);
}

} // namespace

void SMSOracle_onStateChange(u8 state)
{
	if (state == TMarDirector::STATE_UNK1)
		arm();
	if (!sArmed)
		return;
	OSReport("O state tick=%u frame=%u state=%u\n", sLastTick, sFrame, state);
}

void SMSOracle_onPadRead(PADStatus* status)
{
	if (!sArmed)
		return;
	++sFrame;
	if (!sLoaded)
		return;

	// the frame this read feeds ends on sLastTick + ticks per frame
	u32 endTick = sLastTick + sTicksPerFrame;
	s32 n       = -1;
	if (endTick >= sHeader.firstRecordTick) {
		u32 d = endTick - sHeader.firstRecordTick;
		if (d % sTicksPerFrame != 0)
			OSReport("O warn: frame end tick %u is not aligned to the "
			         "first record tick\n",
			         endTick);
		n = d / sTicksPerFrame;
		if ((u32)n >= sHeader.recordCount)
			n = -1;
	}

	PADStatus* p = &status[0];
	p->err       = PAD_ERR_NONE;
	if (n < 0) {
		p->button = 0;
		p->stickX = p->stickY = p->substickX = p->substickY = 0;
		p->triggerLeft = p->triggerRight = 0;
		p->analogA = p->analogB = 0;
		OSReport("I frame=%u tick=%u rec=-\n", sFrame, sLastTick);
		return;
	}
	const Record& r = sRecords[n];
	p->button       = r.buttons;
	p->stickX       = r.stickX;
	p->stickY       = r.stickY;
	p->substickX    = r.substickX;
	p->substickY    = r.substickY;
	p->triggerLeft  = r.triggerL;
	p->triggerRight = r.triggerR;
	p->analogA      = r.analogA;
	p->analogB      = r.analogB;
	OSReport("I frame=%u tick=%u rec=%d b=%04x x=%d y=%d cx=%d cy=%d l=%u r=%u\n",
	         sFrame, sLastTick, n, r.buttons, r.stickX, r.stickY, r.substickX,
	         r.substickY, r.triggerL, r.triggerR);
}

void SMSOracle_onTick(u32 tickCount, u32, u32 cue)
{
	if (!sArmed)
		return;
	sLastTick = tickCount - sArmTick;
	if (sLoaded
	    && (sLastTick < sHeader.firstLogTick || sLastTick > sHeader.lastLogTick))
		return;

	TMario* mario = gpMarioOriginal;
	if (!mario)
		return;
	s32 water = mario->mWaterGun ? mario->mWaterGun->mCurrentWater : -1;
	extern size_t next; // MSL rand() state
	OSReport("T %u %u %u %u %u st=%08x p=%08x %08x %08x v=%08x %08x %08x "
	         "fv=%08x yaw=%04x w=%d cp=%08x %08x %08x ct=%08x %08x %08x "
	         "rng=%08x\n",
	         sLastTick, sFrame, gpMarDirector->mState, gpMarDirector->unk124,
	         cue ? 1 : 0, mario->mStatus, fbits(mario->mPosition.x),
	         fbits(mario->mPosition.y), fbits(mario->mPosition.z),
	         fbits(mario->mVel.x), fbits(mario->mVel.y), fbits(mario->mVel.z),
	         fbits(mario->mForwardVel), (u16)mario->mFaceAngle.y, water,
	         fbits(gpCamera->mPosition.x), fbits(gpCamera->mPosition.y),
	         fbits(gpCamera->mPosition.z), fbits(gpCamera->mTarget.x),
	         fbits(gpCamera->mTarget.y), fbits(gpCamera->mTarget.z), (u32)next);
}
