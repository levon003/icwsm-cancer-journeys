import os, sqlite3

def get_db():
    journal_wd="/home/srivbane/shared/caringbridge/data/derived/sqlite"
    db_filename = os.path.join(journal_wd, "journal.db")
    db = sqlite3.connect(
            db_filename,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
    db.row_factory = sqlite3.Row
    return db

def get_journal_text(site_id, journal_oid):
    try:
        db = get_db()
        cursor = db.execute("""SELECT body 
                                FROM journal
                                WHERE site_id = ? AND journal_oid = ?""", 
                            (site_id, journal_oid))
        body = cursor.fetchone()
        assert body is not None
        body_text = body['body']
        return body_text
    finally:
        db.close()


def get_journal_db():
    journal_wd="/home/srivbane/shared/caringbridge/data/derived/sqlite"
    db_filename = os.path.join(journal_wd, "journal.db")
    db = sqlite3.connect(
            db_filename,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
    db.row_factory = sqlite3.Row
    return db

def get_journal_metadata_db():
    journal_wd="/home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/extract_site_features"
    db_filename = os.path.join(journal_wd, "journal_metadata.db")
    db = sqlite3.connect(
            db_filename,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
    db.row_factory = sqlite3.Row
    return db

def get_site_journal_oids(site_id):
    try:
        db = get_db()
        cursor = db.execute("""SELECT journal_oid 
                                FROM journal
                                WHERE site_id = ?""", 
                            (site_id,))
        result = cursor.fetchall()
        journal_oids = [r['journal_oid'] for r in result]
        return journal_oids
    finally:
        db.close()
        
def get_site_journals(site_id, columns=["*"]):  # directly returns the journal rows associated with the given site_id
    try:
        db = get_db()
        columns_string = ",".join(columns)
        cursor = db.execute("""SELECT {columns}
                                FROM journal
                                WHERE site_id = ?""".format(columns=columns_string), 
                            (site_id,))
        journals = cursor.fetchall()
        return journals
    finally:
        db.close()

def get_journal_text_all(site_id):
    journal_oids = get_site_journal_oids(site_id)
    list_to_be_returned = []
    for journal_id in journal_oids:
        list_to_be_returned.append(get_journal_text(site_id,journal_id))
    return list_to_be_returned

def get_site_journal_oid(site_id):
    site_id = int(site_id)
    # all of this should be in a 'try...finally' block so that the database object is properly closed
    # if it's not, the database might be stuck in a "locked" mode, and no one will be able to read or write to it!
    try:
        db = get_journal_metadata_db()
        # immediately after the 'try', we get access to the db object
        # next, we execute a query by providing the string for the query along with any parameters
        # note that the query uses two parameters in the WHERE clause:
        # - the first is provided in the second argument to db.execute and is marked by the '?'
        # - the second is hardcoded into the query to create the behavior needed by this function
        cursor = db.execute("""SELECT journal_oid 
                                FROM journalMetadata
                                WHERE site_id = ?""", 
                            (site_id,))
        response = cursor.fetchall()
        assert response is not None
        journal_oid = [response[x]['journal_oid'] for x in range(len(response))]
        return journal_oid
    finally:
        db.close()
