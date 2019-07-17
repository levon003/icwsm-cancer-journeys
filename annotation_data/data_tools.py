import sqlite3
import numpy as np
import pandas as panda
from db import get_journal_db, get_journal_metadata_db

def get_first_journal_ts_from(site_id): # Retrieve the timestamp from the first journal of the site at site_id.
    site_id = int(site_id)
    try:
        db = get_journal_metadata_db()
        cursor = db.execute("""SELECT created_at
                                FROM journalMetadata
                                WHERE site_id = ? AND site_index = 0""", 
                            (site_id,))
        response = cursor.fetchone()
        assert response is not None
        journal_date = np.min(response['created_at'])
        return journal_date
    finally:
        db.close()

def get_weeks_since_first_from(site_id, journal_oid): # Compare each journal to its primary post timestamp using the preceding function.
    # Time constant
    ms_in_weeks = 1000 * 60 * 60 * 24 * 7  
                 # ms  * s  * hr * dy * wk
    site_id = int(site_id)
    try:
        db = get_journal_db()
        cursor = db.execute("""SELECT createdAt
                                FROM journal
                                WHERE site_id = ? AND journal_oid = ?""", 
                            (site_id, journal_oid))
        response = cursor.fetchone()
        assert response is not None
        return np.min((np.min(response['createdAt']) - get_first_journal_ts_from(site_id))) / ms_in_weeks
    finally:
        db.close()

def get_site_id(df, journal_oid): # Condenses site_id retrieval from journal_oid into a pretty little function.
    row = df.loc[df['journal_oid'] == journal_oid]
    return row["site_id"]
