DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS journalAnnotation;
DROP TABLE IF EXISTS journalAnnotationConflictResolution;

CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL
);

CREATE TABLE journalAnnotation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id INTEGER NOT NULL,
  journal_oid TEXT NOT NULL,
  created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  username TEXT NOT NULL,
  annotation_type TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE journalAnnotationConflictResolution (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id INTEGER NOT NULL,
  journal_oid TEXT NOT NULL,
  created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolving_username TEXT NOT NULL,
  annotation_type TEXT NOT NULL,
  resolution_type TEXT,
  correct_username TEXT
);

CREATE TABLE discussionTask (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  site_id INTEGER NOT NULL,
  journal_oid TEXT NOT NULL,
  responsibility TEXT NOT NULL,
  phase TEXT NOT NULL,
  /* batch_id is unique to a (responsibility, evidence_username, reconsider_username, phase) */
  batch_id INTEGER NOT NULL,
  /* discussion_id is unique to a (responsibility, evidence_username, reconsider_username, phase, batch_id) */
  discussion_id INTEGER NOT NULL,
  next_discussion_id INTEGER NOT NULL,
  evidence_username TEXT NOT NULL,
  reconsider_username TEXT NOT NULL
);

CREATE TABLE discussionEntry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  site_id INTEGER NOT NULL,
  journal_oid TEXT NOT NULL,
  responsibility TEXT NOT NULL,
  phase TEXT NOT NULL,
  batch_id INTEGER NOT NULL,
  discussion_id INTEGER NOT NULL,
  evidence_username TEXT NOT NULL,
  reconsider_username TEXT NOT NULL,
  /* All other keys are foreign keys to discussionTask; these three are the only new data */
  highlighted_text TEXT,
  additional_discussion TEXT,
  is_annotation_changed INTEGER NOT NULL /* True == 1, False == 0. This defies convention, but it would be tough to fix now... */
);

CREATE TABLE journalPrediction (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id INTEGER NOT NULL,
  journal_oid TEXT NOT NULL,
  created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  prediction_type TEXT NOT NULL,
  data TEXT NOT NULL,
  probability REAL
);

CREATE INDEX journalPrediction_siteId_journalOid ON journalPrediction (site_id, journal_oid);
CREATE INDEX journalPrediction_predictionType_siteId_journalOid ON journalPrediction (prediction_type, site_id, journal_oid);

