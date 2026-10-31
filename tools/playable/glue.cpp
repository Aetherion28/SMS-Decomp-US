// Linked only into the playable build (tools/build_playable.py).
//
// The playable build links the original objects for units we have no source
// for yet. Those objects call a few weak inline functions out of line that, in
// the retail game, came from another object which our source now inlines
// everywhere, so nothing emits them. Taking their addresses here makes the
// compiler emit the weak copies.
// Add to this list if the link reports another undefined weak function.

#include <Enemy/EnemyManager.hpp>

TSpineEnemyParams* (TEnemyManager::*const playable_glue_getSaveParam)() const
    = &TEnemyManager::getSaveParam;
