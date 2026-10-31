#include <Enemy/Killer.hpp>
#include <Enemy/Enemy.hpp>
#include <Enemy/Conductor.hpp>
#include <Enemy/EffectObj.hpp>
#include <Enemy/SmallEnemy.hpp>
#include <Player/MarioAccess.hpp>
#include <Camera/CameraShake.hpp>
#include <Map/Map.hpp>
#include <Map/MapData.hpp>
#include <Map/MapCollisionData.hpp>
#include <M3DUtil/MActor.hpp>
#include <M3DUtil/MActorAnm.hpp>
#include <MarioUtil/MathUtil.hpp>
#include <MarioUtil/PacketUtil.hpp>
#include <MarioUtil/RumbleMgr.hpp>
#include <MarioUtil/RandomUtil.hpp>
#include <MoveBG/MapObjManager.hpp>
#include <MoveBG/MapObjBlock.hpp>
#include <MoveBG/ItemManager.hpp>
#include <Strategic/Spine.hpp>
#include <Strategic/ObjModel.hpp>
#include <System/MarDirector.hpp>
#include <System/Particles.hpp>
#include <MSound/MSound.hpp>
#include <MSound/MSoundSE.hpp>
#include <MSound/SoundEffects.hpp>
#include <JSystem/JMath.hpp>
#include <JSystem/JUtility/JUTNameTab.hpp>
#include <JSystem/J3D/J3DGraphBase/J3DSys.hpp>
#include <JSystem/J3D/J3DGraphAnimator/J3DModel.hpp>
#include <JSystem/J3D/J3DGraphAnimator/J3DNode.hpp>
#include <JSystem/J3D/J3DGraphAnimator/J3DCluster.hpp>
#include <JSystem/J3D/J3DGraphLoader/J3DModelLoader.hpp>
#include <stdlib.h>
#include <math.h>
#include <macros.h>

// rogue includes needed for matching sinit & bss
#include <MSound/MSSetSound.hpp>
#include <MSound/MSoundBGM.hpp>
#include <M3DUtil/MActorAnm.hpp>

u8 TKiller::mSerialBomb        = 1;
u8 TKiller::mTrampleDie        = 1;
f32 TFlyEnemy::mTestSp         = 2.5f;
int TFlyEnemy::mInvalidTime    = 200;
f32 TFlyEnemy::mTestMarioSpMax = 12.0f;

static TKiller* gpCurKiller;
u8 TKiller::mRollSw;

static const char* killer_bastable[] = {
	"/scene/killer/bas/downkiller_down1.bas", nullptr, nullptr,
	"/scene/killer/bas/killer_search1.bas",   nullptr,
};

TFlyEnemyParams::TFlyEnemyParams(const char* path)
    : TWalkerEnemyParams(path)
    , PARAM_INIT(mSLNormalFlyGravityY, 0.2f)
    , PARAM_INIT(mSLNormalFlySpeed, 10.0f)
    , PARAM_INIT(mSLChaseFlyGravityY, 0.1f)
    , PARAM_INIT(mSLChaseDist, 2000.0f)
    , PARAM_INIT(mSLForceGravityY, 0.1f)
{
	TParams::load(mPrmPath);
}

void TFlyEnemy::init(TLiveManager* manager)
{
	TWalkerEnemy::init(manager);
	unk19C = (TFlyEnemyParams*)getSaveParam();
}

f32 TFlyEnemy::getGravityY() const
{
	if (mSpine->getCurrentNerve() == &TNerveFlyEnemyChaseFly::theNerve())
		return unk194;

	return unk19C->mSLNormalFlyGravityY.get();
}

void TFlyEnemy::reset()
{
	TWalkerEnemy::reset();
	unk1A0 = 0;
	unk198 = 1;
	unk1A4 = 0;
	unk194 = unk19C->mSLNormalFlyGravityY.get();
	unk1A5 = 0;
}

void TFlyEnemy::fly()
{
	JGeometry::TVec3<f32> pos = mPosition;
	pos += mPositionDelta;

	JGeometry::TVec3<f32> vel = mVelocity;
	vel.x += *gpMarioSpeedX / mTestMarioSpMax;
	vel.z += *gpMarioSpeedZ / mTestMarioSpMax;
	pos += vel;
	pos.y += unk194;

	mGroundHeight
	    = gpMap->checkGround(pos.x, pos.y + mHeadHeight, pos.z, &mGroundPlane);
	mGroundHeight += 1.0f;

	if (pos.y <= mGroundHeight) {
		if (unk1A0 > mInvalidTime) {
			offLiveFlag(LIVE_FLAG_AIRBORNE);
			mVelocity.x = 0.0f;
			mVelocity.y = 0.0f;
			mVelocity.z = 0.0f;
			pos.y       = mGroundHeight;
		}

		if (mGroundPlane->mActor != nullptr) {
			if (mGroundPlane->mActor->isActorType(ACTOR_TYPE_BASKET_REVERSE))
				((TLiveActor*)mGroundPlane->mActor)->kill();
		}

		if (mGroundPlane->checkFlag(0x10))
			kill();
	} else {
		onLiveFlag(LIVE_FLAG_AIRBORNE);
	}

	mPositionDelta = pos - mPosition;
}

void TFlyEnemy::calcChaseParam()
{
	JGeometry::TVec3<f32> toMario(SMS_GetMarioPos().x - mPosition.x,
	                              SMS_GetMarioPos().y - mPosition.y,
	                              SMS_GetMarioPos().z - mPosition.z);
	toMario.x *= 1.1f;
	toMario.z *= 1.1f;

	JGeometry::TVec3<f32> goal(mPosition.x + toMario.x, mPosition.y + toMario.y,
	                           mPosition.z + toMario.z);
	if (unk1A5)
		setGoalPath(TPathNode(goal));

	if (toMario.y > 100.0f || abs(toMario.y) < 100.0f) {
		if (unk1A5) {
			if (unk198 != 2 && mSprayedByWaterCooldown == 0)
				unk194 = unk19C->mSLChaseFlyGravityY.get();
			unk198 = 2;
		} else {
			mPosition.y -= 1.0f;
		}
		return;
	}

	unk194 = unk19C->mSLNormalFlyGravityY.get();
	JGeometry::TVec3<f32> vel(0.0f, 0.0f, 0.0f);
	if (unk198 != 2 || toMario.y > 150.0f) {
		unk198 = 0;
		MsVECNormalize(&toMario, &toMario);
		f32 speed = unk19C->mSLNormalFlySpeed.get();
		vel.x     = toMario.x * speed;
		vel.z     = toMario.z * speed;
		unk194 = unk19C->mSLForceGravityY.get();
	} else {
		mPosition.y -= 3.0f;
	}

	vel.z     = 0.0f;
	vel.x     = 0.0f;
	mVelocity = vel;
}

void TFlyEnemy::bind()
{
	if (mSpine->getCurrentNerve() == &TNerveFlyEnemyChaseFly::theNerve()
	    || unk1A0 < mInvalidTime)
		fly();
	else
		TLiveActor::bind();
}

// fabricated
static inline void calcFlyVec(JGeometry::TVec3<f32>& v, f32 angle, f32 speed)
{
	v.set(speed * MsSin(angle), 0.0f, speed * MsCos(angle));
}

// TODO: in the target, MsSin, MsCos and TVec3::set<f32> stay out-of-line
// calls inside the copy of this function inlined into
// TNerveFlyEnemyChaseFly::execute, so the real inline nesting here is deeper
// than this reconstruction.
void TFlyEnemy::flyMove()
{
	JGeometry::TVec3<f32> vel = getVelocity();
	vel *= 0.9f;
	setVelocity(vel);


	JGeometry::TVec3<f32> toGoal = unkF4.getPoint();
	toGoal -= mPosition;
	PSVECMag(&toGoal);

	f32 target = MsWrap(MsGetRotFromZaxisY(toGoal), 0.0f, 360.0f);
	f32 diff   = target - MsWrap(mRotation.y, target - 180.0f, target + 180.0f);
	mRotation.y
	    = MsWrap(mRotation.y
	                 + (diff > 0.0f ? (diff > mTurnSpeed ? mTurnSpeed : diff)
	                                : (diff > -mTurnSpeed ? diff : -mTurnSpeed)),
	             0.0f, 360.0f);

	JGeometry::TVec3<f32> delta = mPositionDelta;
	JGeometry::TVec3<f32> move;
	calcFlyVec(move, mRotation.y, mMarchSpeed);
	delta += move;
	mPositionDelta = delta;
}

DEFINE_NERVE(TNerveFlyEnemyNormalFly, TLiveActor)
{
	TFlyEnemy* self = (TFlyEnemy*)spine->getBody();

	if (spine->getTime() == 0)
		self->setNormalFlyAnm();

	if (self->unk1A4 && self->unk1A0 > 500) {
		self->updateSquareToMario();
		if (self->mDistToMarioSquared < self->unk19C->mSLChaseDist.get()
		                                    * self->unk19C->mSLChaseDist.get()) {
			spine->pushAfterCurrent(&TNerveFlyEnemyChaseFly::theNerve());
			return true;
		}
	} else if (!self->unk1A6 && self->isFindMario(1.0f)
	           && self->unk1A0 > 100) {
		self->updateSquareToMario();
		if (self->mDistToMarioSquared < self->unk19C->mSLChaseDist.get()
		                                    * self->unk19C->mSLChaseDist.get()) {
			spine->pushAfterCurrent(&TNerveFlyEnemyChaseFly::theNerve());
			return true;
		}
	}

	self->mRotation.x = MsGetRotFromZaxis(self->getVelocity()).x;
	f32 scale = MsClamp(1.05f * self->mScaling.x, 0.0f, self->getBodyScale());
	self->mScaling.x = self->mScaling.y = self->mScaling.z = scale;
	return false;
}

DEFINE_NERVE(TNerveFlyEnemyChaseFly, TLiveActor)
{
	TFlyEnemy* self = (TFlyEnemy*)spine->getBody();

	if (spine->getTime() == 0) {
		self->unk1A8 = self->mVelocity;
		self->calcChaseParam();
		self->setChaseFlyAnm();
	}

	f32 walkRate = 1.0f;
	if (!self->unk1A5) {
		f32 march2     = self->getMarchSpeed() * self->getMarchSpeed();
		self->unk1A8.y = 0.1f;
		walkRate       = self->unk1A8.length() / march2 * TFlyEnemy::mTestSp;
	} else if (self->unk198 == 0) {
		walkRate = 2.0f;
	}
	self->walkBehavior(2, walkRate);

	if ((self->unk1A5 && self->isReachedToGoalXZ())
	    || (self->unk198 == 0
	        && self->mPosition.y < 100.0f + self->mGroundHeight))
		self->calcChaseParam();

	switch (self->unk198) {
	case 0:
	case 1:
		self->walkBehavior(3, 1.0f);
		break;
	case 2:
		self->flyMove();
		break;
	}

	if (self->unk198 != 2
	    && self->mPosition.y > 200.0f + self->mGroundHeight) {
		JGeometry::TVec3<f32> dir(self->getMarchSpeed(),
		                          -40.0f * self->getGravityY(),
		                          self->getMarchSpeed());
		self->mRotation.x = MsGetRotFromZaxis(dir).x;

		JGeometry::TVec3<f32> delta = self->mPositionDelta;
		delta.y                     = self->getGravityY();
		self->mRotation.x           = MsGetRotFromZaxis(delta).x;
	} else {
		self->mRotation.x *= 0.99f;
	}

	self->flyBehavior();

	f32 scale = MsClamp(1.1f * self->mScaling.x, 0.0f, self->getBodyScale());
	self->mScaling.x = self->mScaling.y = self->mScaling.z = scale;
	return false;
}

TKillerSaveLoadParams::TKillerSaveLoadParams(const char* path)
    : TFlyEnemyParams(path)
    , PARAM_INIT(mSLWaterAddGravityY, 1.0f)
    , PARAM_INIT(mSLChaseTimer, 1000)
    , PARAM_INIT(mSLBombRange, 300.0f)
{
	TParams::load(mPrmPath);
}

TKillerManager::TKillerManager(const char* name)
    : TSmallEnemyManager(name)
{
	gpCurKiller = nullptr;
}

void TKillerManager::load(JSUMemoryInputStream& stream)
{
	TSmallEnemyManager::load(stream);
	unk38 = new TKillerSaveLoadParams("/enemy/killer.prm");
}

void TKillerManager::createModelData()
{
	static TModelDataLoadEntry entry[] = {
		{ "killer_model1.bmd", 0x10220000, 0 },
		{ "downkiller_model1.bmd", 0x10220000, 0 },
		{ nullptr, 0, 0 },
	};

	createModelDataArray(entry);
}

// TODO: the target spills the new object to the stack and calls the
// TMtx34f constructor out of line; the inlining depth differs here.
TSpineEnemy* TKillerManager::createEnemyInstance() { return new TKiller; }

// TODO: the target keeps &rollMtx in a register and has a 0x10 bigger frame,
// as does genEventCoin with its rotation matrix; some matrix helper is missing.
static BOOL KillerBodyCallback(J3DNode* node, int calc)
{
	if (calc == 0) {
		TKiller* killer = gpCurKiller;
		if (killer == nullptr || !TKiller::mRollSw || !killer->isRollFly())
			return TRUE;

		MtxPtr anmMtx = gpCurKiller->getModel()->getAnmMtx(
		    ((J3DJoint*)node)->getJntNo());

		// TODO: the target keeps &rollMtx in r31 for both concats with it,
		// as if it were read through a pointer.
		TPosition3f scaleMtx;
		Mtx rollMtx;
		scaleMtx.zeroTrans();
		f32 scale = gpCurKiller->getBodyScale();
		scaleMtx.setScale(scale, scale, scale);
		MsMtxSetRotZ(rollMtx, gpCurKiller->unk1B8);

		MTXConcat(anmMtx, rollMtx, anmMtx);
		MTXConcat(anmMtx, scaleMtx, anmMtx);
		MTXConcat(J3DSys::mCurrentMtx, rollMtx, J3DSys::mCurrentMtx);
		MTXConcat(J3DSys::mCurrentMtx, scaleMtx, J3DSys::mCurrentMtx);
	}
	return TRUE;
}

TKiller::TKiller(const char* name)
    : TFlyEnemy(name)
{
}

void TKiller::init(TLiveManager* manager)
{
	TWalkerEnemy::init(manager);
	unk19C      = (TFlyEnemyParams*)getSaveParam();
	mActorType  = ACTOR_TYPE_ENEMY_UNK1F;
	unk150      = 17;
	unk1B4      = getSaveParam2();
	mSpine->initWith(&TNerveFlyEnemyNormalFly::theNerve());
	onLiveFlag(LIVE_FLAG_FORCE_SHADOW);
	offLiveFlag(LIVE_FLAG_UNK800);
	onHitFilter(HIT_CATEGORY_MAP_OBJECT);

	J3DModel* model = getMActor()->getModel();
	if (model->getSkinDeform() == nullptr) {
		J3DSkinDeform* deform = new J3DSkinDeform;
		model->setSkinDeform(deform, J3D_DEFORM_ATTACH_FLAG_UNK_1);
	}
	getMActor()->resetDL();

	if (mInstanceIndex == 0) {
		for (u8 i = 0; i < getModel()->getModelData()->getJointNum(); i++)
			;
	}

	getMActor()->setJointCallback(1, KillerBodyCallback);
	unk188 = 0.0f;
}

void TKiller::setMActorAndKeeper()
{
	mMActorKeeper = new TMActorKeeper(mManager, 2);
	mMActor       = mMActorKeeper->createMActor("killer_model1.bmd", 3);
	mMActorKeeper->createMActor("downkiller_model1.bmd", 3);

	s32 noseMatIdx = getActorKeeper()
	                     ->getMActor("killer_model1.bmd")
	                     ->getModel()
	                     ->getModelData()
	                     ->getMaterialName()
	                     ->getIndex("_nosemat1");
	s32 eyesMatIdx = getActorKeeper()
	                     ->getMActor("killer_model1.bmd")
	                     ->getModel()
	                     ->getModelData()
	                     ->getMaterialName()
	                     ->getIndex("_eyesmat1");
	s32 bodyMatIdx = getActorKeeper()
	                     ->getMActor("killer_model1.bmd")
	                     ->getModel()
	                     ->getModelData()
	                     ->getMaterialName()
	                     ->getIndex("_body1");

	SMS_InitPacket_OneTevColor(getMActor()->getModel(), noseMatIdx, GX_TEVREG0,
	                           &mNoseColor);
	SMS_InitPacket_OneTevColor(getMActor()->getModel(), eyesMatIdx, GX_TEVREG0,
	                           &mEyesColor);
	SMS_InitPacket_OneTevColor(getMActor()->getModel(), bodyMatIdx, GX_TEVREG0,
	                           &mBodyColor);
	SMS_InitPacket_OneTevColor(
	    getActorKeeper()->getMActor("downkiller_model1.bmd")->getModel(),
	    bodyMatIdx, GX_TEVREG0, &mBaseColor);
}

void TKiller::behaveToWater(THitActor* water)
{
	if (mSpine->getCurrentNerve() == &TNerveFlyEnemyNormalFly::theNerve()
	    || mSpine->getCurrentNerve() == &TNerveFlyEnemyChaseFly::theNerve())
		genEventCoin();

	if (mSpine->getCurrentNerve() != &TNerveKillerExplosion::theNerve()) {
		mSpine->pushNerve(&TNerveKillerExplosion::theNerve());
		onHitFilter(HIT_FILTER_NO_COLLISION);
		mVelocity = JGeometry::TVec3<f32>(0.0f, 0.0f, 0.0f);
	}
}

void TKiller::genEventCoin()
{
	int num = 2;
	if (unk1A6)
		num = 8;

	for (int i = 0; i < num; i++) {
		JGeometry::TVec3<f32> offset(0.0f, 0.0f, 30.0f);
		Mtx rot;
		MsMtxSetRotY(rot, 360.0f * (1.0f / num) * (i + 1));
		MTXMultVec(rot, &offset, &offset);

		TLiveActor* coin = (TLiveActor*)gpItemManager->makeObjAppear(
		    mPosition.x + offset.x, mPosition.y, mPosition.z + offset.z,
		    0x2000000E, true);
		if (coin != nullptr) {
			coin->mPosition.y = mPosition.y;
			MsVECNormalize(&offset, &offset);
			coin->mVelocity.set(3.0f * offset.x, 20.0f, 3.0f * offset.z);
			coin->offLiveFlag(LIVE_FLAG_UNK10);
		}
	}
}

bool TKiller::isHitValid(u32 message)
{
	if (message == HIT_MESSAGE_UNKB) {
		onLiveFlag(LIVE_FLAG_DEAD);
		onHitFilter(HIT_FILTER_NO_COLLISION);
		genEventCoin();
		return false;
	}

	if (mTrampleDie)
		unk194 -= 12.0f;

	return false;
}

void TKiller::setDeadAnm()
{
	mMActor = getActorKeeper()->getMActor("downkiller_model1.bmd");
	setBckAnm(0);
	TEffectExplosion* effect
	    = (TEffectExplosion*)gpConductor->makeOneEnemyAppear(
	        mPosition, "エフェクト爆発マネージャー", 1);
	if (effect != nullptr)
		effect->generate(mPosition, mScaling);
	gpCameraShake->startShake(CAM_SHAKE_MODE_UNK6, 1.0f);
	SMSRumbleMgr->start(0x15, 5, (f32*)nullptr);
}

void TKiller::attackToMario()
{
	if (SMS_GetMarioPos().y < mPosition.y) {
		if (mSpine->getCurrentNerve() != &TNerveKillerExplosion::theNerve()) {
			mSpine->pushNerve(&TNerveKillerExplosion::theNerve());
			sendAttackMsgToMario();
		} else {
			SMS_SendMessageToMario(this, HIT_MESSAGE_BURN);
		}
	}
}

const char** TKiller::getBasNameTable() const { return killer_bastable; }

void TKiller::setNormalFlyAnm()
{
	mMActor = getActorKeeper()->getMActor("killer_model1.bmd");
	setBckAnm(2);
	unk1B8 = 0.0f;
	unk1A0 = 0;
}

void TKiller::setChaseFlyAnm() { setBckAnm(3); }

bool TKiller::isRollFly()
{
	if (mSpine->getCurrentNerve() == &TNerveFlyEnemyChaseFly::theNerve()
	    && isBckAnm(1))
		return true;
	return false;
}

bool TKiller::isCollidMove(THitActor* actor)
{
	if (actor->isActorType(ACTOR_TYPE_BASKET_REVERSE))
		((TLiveActor*)actor)->kill();

	if (mSerialBomb
	    && mSpine->getCurrentNerve() == &TNerveFlyEnemyChaseFly::theNerve())
		mSpine->pushNerve(&TNerveKillerExplosion::theNerve());

	return true;
}

void TKiller::flyBehavior()
{
	mTurnSpeed = unk1B4->mSLTurnSpeedLow.get();
	if (mSpine->getTime() > unk1B4->mSLChaseTimer.get())
		unk194 -= unk1B4->mSLWaterAddGravityY.get();

	if (checkCurAnmEnd(0) && isBckAnm(3))
		setBckAnm(1);

	unk1B8 += 2.5f;
}

void TKiller::changeOut()
{
	SMSGetMSound()->startSoundActor(MSD_SE_EN_TELSA_RECOVER, &mPosition, 0,
	                                nullptr, 0, 4);
	onLiveFlag(LIVE_FLAG_DEAD);
	genEventCoin();
	onHitFilter(HIT_FILTER_NO_COLLISION);
	mPosition = mJuiceBlock->mPosition;
	gpMarioParticleManager->emitAndBindToPosPtr(PARTICLE_MS_TLS_CHANGE,
	                                            &mPosition, 0, nullptr);
	getMActor()->setFrameRate(SMSGetAnmFrameRate(), ANM_TYPE_BCK);
	mJuiceBlock->kill();
	mJuiceBlock = nullptr;
}

void TKiller::reset()
{
	gpCurKiller = this;
	TWalkerEnemy::reset();
	unk1A0 = 0;
	unk198 = 1;
	unk1A4 = 0;
	unk194 = unk19C->mSLNormalFlyGravityY.get();
	unk1A5 = 0;

	TMsRange<f32> range(0.0f, 1.0f);
	mBodyColor.r = mBodyColor.g = mBodyColor.b = mBaseColor.r = mBaseColor.g
	    = mBaseColor.b                         = 0;
	unk1A6 = 0;
	if (range.rand() < 0.05f) {

		unk1A6       = 1;
		mBodyColor.r = 200;
		mBodyColor.g = 185;
		mBodyColor.b = 0;
		mBaseColor.r = 255;
		mBaseColor.g = 225;
		mBaseColor.b = 70;
	}
}

void TKiller::setColorType()
{
	if (unk1A6)
		unk1A5 = 0;

	if (unk1A5) {
		mBodyColor.r = 70;
		mBodyColor.g = 20;
		mBodyColor.b = 70;
		mBaseColor.r = 70;
		mBaseColor.g = 20;
		mBaseColor.b = 70;
	}
}

void TKiller::bind()
{
	TFlyEnemy::bind();
	unk1A0++;

	if (mSpine->getCurrentNerve() != &TNerveKillerExplosion::theNerve()) {
		if (!isAirborne() && unk1A0 > mInvalidTime) {
			mSpine->pushNerve(&TNerveKillerExplosion::theNerve());
		} else if (unk1A0 > mInvalidTime) {
			TBGWallCheckRecord record(mPosition.x, mPosition.y + mHeadHeight,
			                          mPosition.z, 2.0f * mBodyRadius, 1, 0);
			if (gpMap->isTouchedWallsAndMoveXZ(&record)) {
				if (record.mResultWalls[0]->mActor != nullptr) {
					if (record.mResultWalls[0]->mActor->isActorType(
					        ACTOR_TYPE_BASKET_REVERSE))
						((TLiveActor*)record.mResultWalls[0]->mActor)->kill();
				}
				mSpine->pushNerve(&TNerveKillerExplosion::theNerve());
			}
		}
	}

	if (isAirborne()) {
		SMSGetMSound()->startSoundActor(MSD_SE_EN_KILLER_FLY, &mPosition, 0,
		                                nullptr, 0, 4);
		mRotation.x = MsClamp(mRotation.x, -25.0f, 90.0f);
		MsMtxSetXYZRPH(mSmokeMtx, mPosition.x, mPosition.y, mPosition.z,
		               mRotation.x, mRotation.y, mRotation.z);
		gpMarioParticleManager->emitAndBindToMtxPtr(PARTICLE_MS_KIL_SMOKE,
		                                            mSmokeMtx, 1, this);
	}
}

void TKiller::calcRootMatrix()
{
	if (gpMarDirector->checkFlag(0xF)) {
		onLiveFlag(LIVE_FLAG_DEAD);
		onHitFilter(HIT_FILTER_NO_COLLISION);
	}

	if (isBckAnm(2)) {
		if (unk1A6) {
			mNoseColor.r = mEyesColor.r = 170;
			mNoseColor.g = mEyesColor.g = 140;
			mNoseColor.b = mEyesColor.b = 0;
		} else {
			mNoseColor.r = mNoseColor.g = mNoseColor.b = mEyesColor.r
			    = mEyesColor.g = mEyesColor.b = 0;
		}
	}

	if (isBckAnm(3)) {
		mNoseColor.b = 0;
		mNoseColor.g = 0;
		mEyesColor.r = 0;
		if (mSpine->getTime() % 10 < 5) {
			mNoseColor.r = 0;
			mEyesColor.b = 0;
			mEyesColor.g = 0;
		}

		if (unk1A6) {
			if (mSpine->getTime() % 10 < 5) {
				mNoseColor.r = 170;
				mNoseColor.g = 140;
				mNoseColor.b = 0;
			} else {
				mNoseColor.r = 180;
				mNoseColor.g = 140;
				mNoseColor.b = 150;
			}
		}

		if (unk1A5) {
			if (mSpine->getTime() % 10 < 5) {
				mNoseColor.r = mEyesColor.r = 200;
				mNoseColor.g = 0;
				mNoseColor.b = 0;
			} else {
				mNoseColor.r = 70;
				mNoseColor.g = 20;
				mNoseColor.b = 70;
			}
		}
	}

	if (isBckAnm(1)) {
		mEyesColor.r = 0;
		mEyesColor.b = 0;
		mEyesColor.g = 0;
		mNoseColor.b = 0;
		mNoseColor.g = 0;

		f32 glow = fabsf(MsSin(360.0f * mSpine->getTime() / 120.0f));
		if (unk1A6) {
			mBodyColor.r = 170;
			mBodyColor.g = 140;
			mBodyColor.b = 0;
			mNoseColor.r = (u8)(10.0f * glow + 160.0f);
			mNoseColor.g = (u8)(30.0f * glow + 140.0f);
			mNoseColor.b = (u8)(150.0f * glow);
		}

		if (unk1A5) {
			mBodyColor.r = 70;
			mBodyColor.g = 20;
			mBodyColor.b = 70;
			mBaseColor.r = 70;
			mBaseColor.g = 20;
			mBaseColor.b = 70;
			mNoseColor.r = (u8)(130.0f * glow + 70.0f);
			mNoseColor.g = (u8)-(20.0f * glow - 20.0f);
			mNoseColor.b = (u8)-(70.0f * glow - 70.0f);
		}
	}

	gpCurKiller = this;
	mRotation.x = MsClamp(mRotation.x, -25.0f, 90.0f);
	TSpineEnemy::calcRootMatrix();
}

bool TKiller::isFindMario(f32 param_1)
{
	TSmallEnemyParams* prms = getSaveParams();

	f32 searchHeight = prms->mSLSearchHeight.get();

	if (abs(SMS_GetMarioPos().y - mPosition.y) < searchHeight) {
		JGeometry::TVec3<f32> marioPos = SMS_GetMarioPos();

		f32 searchLength = prms->mSLSearchLength.get();
		f32 searchAngle  = prms->mSLSearchAngle.get();
		f32 searchAware  = prms->mSLSearchAware.get();

		if (isInSight(marioPos, searchLength * param_1, searchAngle * param_1,
		              searchAware * param_1))
			return true;
		else
			return false;
	}

	return false;
}

DEFINE_NERVE(TNerveKillerExplosion, TLiveActor)
{
	TKiller* self = (TKiller*)spine->getBody();

	if (spine->getTime() == 0) {
		self->unk20C = self->getSaveParam2()->mSLBombRange.get()
		               * self->getBodyScale() / self->getAttackRadius();
		self->mRotation.x = 0.0f;
		self->setDeadAnm();

		if (!self->isAirborne()) {
			if (self->mGroundPlane->isWaterSurface()) {
				TEffectBombColumWater* effect
				    = (TEffectBombColumWater*)gpConductor->makeOneEnemyAppear(
				        self->mPosition, "エフェクト爆発水柱マネージャー", 1);
				if (effect != nullptr)
					effect->generate(self->mPosition,
					                 JGeometry::TVec3<f32>(2.0f, 2.0f, 2.0f));
			}

			if (self->mGroundPlane->isSand()) {
				TEffectColumSand* effect
				    = (TEffectColumSand*)gpConductor->makeOneEnemyAppear(
				        self->mPosition, "エフェクト砂柱マネージャー", 1);
				if (effect != nullptr)
					effect->generate(self->mPosition,
					                 JGeometry::TVec3<f32>(0.6f, 0.9f, 0.6f));
			}
		}

		SMSRumbleMgr->start(0x13, &self->mPosition);
	}

	if (self->unk190 < self->unk20C) {
		self->unk190 *= 1.3f;
	} else {
		self->onHitFilter(HIT_FILTER_NO_COLLISION);
		if (self->checkCurAnmEnd(0)) {
			self->onLiveFlag(LIVE_FLAG_DEAD);
			self->onLiveFlag(LIVE_FLAG_UNK8);
			self->offLiveFlag(TSmallEnemy::LIVE_FLAG_MELT_ON_DEATH);
			self->mHolder = nullptr;
			self->stopAnmSound();
			spine->reset();

			spine->setNext(&TNerveSmallEnemyDie::theNerve());
			spine->pushAfterCurrent(spine->getDefault());
			self->mPosition.y -= 200.0f;
			return true;
		}
	}

	self->expandCollision();
	return false;
}
