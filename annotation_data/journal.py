
from html.parser import HTMLParser

from db import get_journal_db

DUMMY_JOURNAL = "This CaringBridge site was created just recently."


def get_journal(site_id, journal_oid):
    site_id = int(site_id)
    try:
        db = get_journal_db()
        cursor = db.execute("""SELECT id, title, body 
                                    FROM journal 
                                    WHERE site_id = ? AND journal_oid = ?
                                    ORDER BY createdAt DESC""",
                            (site_id, journal_oid))
        journals = cursor.fetchall()
        assert journals is not None, "No journal with this site_id/journal_oid"
        assert len(journals) == 1, f"len(journals) journals with this site_id/journal_oid"

        def get_length(title, body):
            title_len = 0 if title is None else len(title)
            body_len = 0 if body is None else len(body)
            return title_len + body_len

        j = journals[0]
        journal_dict = {'site_id': site_id,
                          'journal_oid': journal_oid,
                          'text_length': get_length(j['title'], j['body']),
                          'title': j['title'],
                          'body': j['body']}
        return journal_dict
    finally:
        db.close()


def get_journal_text(site_id, journal_oid):
    return get_journal_text_representation(get_journal(site_id, journal_oid))


def get_journal_info(site_id):
    site_id = int(site_id)
    try:
        db = get_journal_db()
        cursor = db.execute("""SELECT id, journal_oid, title, body, createdAt
                                FROM journal 
                                WHERE site_id = ?
                                ORDER BY createdAt""",
                            (site_id,))
        journals = cursor.fetchall()
        assert journals is not None

        def get_length(title, body):
            title_len = 0 if title is None else len(title)
            body_len = 0 if body is None else len(body)
            return title_len + body_len

        journal_dicts = [{'site_id': site_id,
                          'journal_oid': j['journal_oid'],
                          'journal_index': i,
                          'created_at': int(j['createdAt']),
                          'text_length': get_length(j['title'], j['body']),
                          'title': j['title'],
                          'body': j['body']}
                         for i, j in enumerate(journals)]
        return journal_dicts
    finally:
        db.close()


def get_journal_text_representation(journal):
    if journal is None:
        return None
    title_text = journal['title']
    title_text = "" if title_text is None else title_text
    body_text = journal['body']
    body_text = "" if body_text is None else body_text
    if body_text.startswith(DUMMY_JOURNAL):
        return None
    all_text = title_text + "\n" + body_text
    if len(all_text) < 50:
        return None
    cleaned_text = get_cleaned_text(all_text)
    return cleaned_text


def get_cleaned_text(text):
    stripped = strip_tags(text)
    return stripped.replace("\n", " NEWLINE ")


# See: https://stackoverflow.com/questions/753052/strip-html-from-strings-in-python
class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ' '.join(self.fed)


def strip_tags(html_text):  # this function strips HTML tags from a given text string
    s = MLStripper()
    s.feed(html_text)
    return s.get_data()


def iter_journal_texts(ignore_site_ids=[], limit=-1):
    try:
        db = get_journal_db()
        cursor = db.execute("""SELECT site_id, journal_oid, title, body, createdAt
                                FROM journal""")
        num_returned = 0
        while True:
            journal = cursor.fetchone()
            if journal is None:
                return

            def get_length(title, body):
                title_len = 0 if title is None else len(title)
                body_len = 0 if body is None else len(body)
                return title_len + body_len
            
            if journal['site_id'] in ignore_site_ids:
                continue

            journal_dict = {'site_id': journal['site_id'],
                              'journal_oid': journal['journal_oid'],
                              'created_at': int(journal['createdAt']),
                              'text_length': get_length(journal['title'], journal['body']),
                              'title': journal['title'],
                              'body': journal['body']}
            num_returned += 1
            yield journal_dict
            
            if num_returned == limit:
                # hit the limit, so should stop iterating through the cursor's results
                return
    finally:
        db.close()
