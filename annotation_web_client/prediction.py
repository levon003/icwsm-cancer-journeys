from annotation_web_client.db import get_db

"""
Current types of predictions stored in the database:
- 'journal_author_type': Predictions for if a site is 
"""

def get_journal_prediction(prediction_type, site_id, journal_oid, default=None, return_prob=True):
    db = get_db()
    cursor = db.execute(
        """SELECT data, probability
            FROM journalPrediction 
            WHERE prediction_type = ? AND site_id = ? AND journal_oid = ?
            ORDER BY id DESC""", (prediction_type, site_id, journal_oid)
    )

    latest_prediction = cursor.fetchone()
    if latest_prediction is not None and latest_prediction['data'] != "":
        data = latest_prediction['data']
        prob = float(latest_prediction['probability'])
    else:
        data = default
        prob = None

    if return_prob:
        return data, prob
    else:
        return data


def get_journal_predictions(prediction_type, site_id):
    """
    Returns all predictions of the given type on the jouransl of the given site.
    :param prediction_type:
    :param site_id:
    :return: List of (data, prob) pairs for all journals on the given site. Can be empty.
    """
    db = get_db()
    cursor = db.execute(
        """SELECT data, probability
            FROM journalPrediction 
            WHERE prediction_type = ? AND site_id = ?
            GROUP BY journal_oid
            ORDER BY id DESC""", (prediction_type, site_id)
    )

    predictions = []
    results = cursor.fetchall()
    if results is not None:
        for result in results:
            data = result['data']
            if 'probability' in result and result['probability'] is not None:
                prob = float(result['probability'])
            else:
                prob = None
            predictions.append((data, prob))
    return predictions
