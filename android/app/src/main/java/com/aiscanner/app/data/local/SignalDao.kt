package com.aiscanner.app.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface SignalDao {

    @Query("SELECT * FROM signals_cache ORDER BY cachedAt DESC")
    suspend fun getAll(): List<SignalEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(signals: List<SignalEntity>)

    @Query("DELETE FROM signals_cache")
    suspend fun clear()
}
