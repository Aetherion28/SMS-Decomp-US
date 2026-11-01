#ifndef SYSTEM_BALLOONMSG_HPP
#define SYSTEM_BALLOONMSG_HPP

#if defined(VERSION_GMSP01) || defined(VERSION_GMSE01)                         \
    || defined(VERSION_GMSP01_NX) || defined(VERSION_GMSJ01_01)
#define BALLOON_MSG_PAL_(n) \
	((n) >= 0x31 ? (n) + 3 : (n) >= 0x28 ? (n) - 3 : (n))
#endif

#if defined(VERSION_GMSP01) || defined(VERSION_GMSE01) || defined(VERSION_GMSP01_NX)
#define BALLOON_MSG(id) BALLOON_MSG_PAL_((id) & 0xFFFF)
#elif defined(VERSION_GMSJ01_01)
#define BALLOON_MSG(id) (((id) & 0xFFFF0000) | BALLOON_MSG_PAL_((id) & 0xFFFF))
#else
#define BALLOON_MSG(id) (id)
#endif

#endif // SYSTEM_BALLOONMSG_HPP
