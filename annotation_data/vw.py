
import os
import random
import numpy as np
import pandas as pd

from responsibility import responsibility_labels
from phase import phase_labels

def get_cleaned_text_for_vw(text):
    cleaned_text = text.strip().replace(':', 'COLON').replace('|', 'PIPE').replace("\n", "NEWLINE ")
    return cleaned_text


def format_responsibility_df_as_binary(df, output_dir, identifier="default", include_unannotated=True,
                                      weight_unbalanced_classes=False):
    a_df = df[df.is_annotated]
    un_df = df[~df.is_annotated]
    assert len(a_df) + len(un_df) == len(df)

    train_filenames = ["responsibility_binary_" + resp + "_" + identifier + ".train" 
                       for resp in responsibility_labels]
    test_filename = "responsibility_binary_" + identifier + ".test"

    train_filepaths = [os.path.join(output_dir, train_filename)
                       for train_filename in train_filenames]
    test_filepath = os.path.join(output_dir, test_filename)
    
    if weight_unbalanced_classes:
        resp_weights = []
        for resp_label in responsibility_labels:
            pos_count = np.sum(a_df[resp_label + "_score"] > 0.5)
            neg_count = len(a_df) - pos_count
            if pos_count > neg_count:
                larger, smaller = pos_count, neg_count
                direction = "negative"
            elif pos_count <= neg_count:
                larger, smaller = neg_count, pos_count
                direction = "positive"
            resp_weight = int(larger / smaller)
            print(f"Responsibility {resp_label} will weight {direction} samples with weight {resp_weight}.")
            resp_weights.append(resp_weight)
        assert len(resp_weights) == len(responsibility_labels)
        
    
    # set the random ordering to use for all responsibilities
    shuffled_indices = np.arange(len(a_df))
    np.random.shuffle(shuffled_indices)
    
    for i in range(len(train_filepaths)):
        resp_label, train_filepath = responsibility_labels[i], train_filepaths[i]
        lines = []
        for j in range(len(a_df)):
            journal = a_df.iloc[j]
            journal_text = journal['journal_text']
            identifier = f"sid{journal['site_id']}joid{journal['journal_oid']}"
            label_section = "+1" if journal[resp_label + "_score"] > 0.5 else "-1"
            if weight_unbalanced_classes:
                weight = resp_weights[i]
                formatted_line = f"{label_section} {weight} {identifier}|J {journal_text}\n"
            else:
                formatted_line = f"{label_section} {identifier}|J {journal_text}\n"
            lines.append(formatted_line)
        # shuffle the lines according to the indices computed above
        lines = np.array(lines)[shuffled_indices]
        with open(train_filepath, 'w') as outfile:
            for formatted_line in lines:
                outfile.write(formatted_line)
        print(f"Wrote {len(lines)} train lines to '{train_filepath}' for binary classification of responsibility '{resp_label}'.")
        
    if include_unannotated:
        with open(test_filepath, 'w') as outfile:
            for i in range(len(un_df)):
                journal = un_df.iloc[i]
                journal_text = journal['journal_text']
                identifier = f"sid{journal['site_id']}joid{journal['journal_oid']}"
                formatted_line = f" {identifier}|J {journal_text}\n"
                outfile.write(formatted_line)
        print(f"Wrote {len(un_df)} test lines to '{test_filepath}' for binary classification.")
    
    # return the train and test filepaths so they can be passed to Vowpal Wabbit for training and testing
    return train_filepaths, test_filepath


def format_responsibility_df_as_multiclass(df, output_dir, 
                                           validation_site_ids=None,
                                           identifier="default", 
                                           include_unannotated=True,
                                           resp_subset=responsibility_labels):
    """

    :param df: DataFrame produced by responsibility.get_annotated_responsibility_df()
    :param output_dir: The directory in which generated training and testing files should be written.
    :param identifier: A text identifier appended to the name of all generated files.
    :param include_unannotated: If unannotated entries in the given df should be included.
    :param resp_subset: List of responsibilities to include in the training and testing label set
    :return: train_filepath, test_filepath, holdout_after
    """
    # TODO Allow the ability to specify particular sites/journals as in the validation set
    if len(resp_subset) < 2:
        raise ValueError("Expected at least two responsibilities to classify.")
    if validation_site_ids is None:
        validation_pct = 0.2
        annotated_sites = set(df.site_id)
        validation_site_count = int(len(annotated_sites) * validation_pct)
        print(f"Chose {validation_site_count}/{len(annotated_sites)} sites for validation.")
        validation_site_ids = random.sample(annotated_sites, validation_site_count)
    
    a_df = df[df.is_annotated]
    un_df = df[~df.is_annotated]
    assert len(a_df) + len(un_df) == len(df)

    train_filename = "responsibility_csoaa_" + identifier + ".train"
    test_filename = "responsibility_csoaa_" + identifier + ".test"

    train_filepath = os.path.join(output_dir, train_filename)
    test_filepath = os.path.join(output_dir, test_filename)

    # generate the lines to be written to the output file
    train_lines = []
    validation_lines = []
    for i in range(len(a_df)):
        journal = a_df.iloc[i]
        site_id = journal['site_id']
        journal_text = get_cleaned_text_for_vw(journal['journal_text'])
        identifier = f"sid{site_id}joid{journal['journal_oid']}"

        label_section = ""
        for resp_label in resp_subset:
            resp_score = journal[resp_label + "_score"]
            vw_score = 1.0 - resp_score  # since CSOAA weights are inverted...
            label_section += f"{resp_label}:{vw_score} "

        formatted_line = f"{label_section} {identifier}|J {journal_text}\n"
        if site_id in validation_site_ids:
            validation_lines.append(formatted_line)
        else:
            train_lines.append(formatted_line)
    # need to randomize the ordering of the training lines in the file
    random.shuffle(train_lines)
    # now, write the lines to a file
    lines_written = 0
    with open(train_filepath, 'w') as outfile:
        for formatted_line in train_lines:
            outfile.write(formatted_line)
            lines_written += 1
        for formatted_line in validation_lines:
            outfile.write(formatted_line)
            lines_written += 1
    print(f"Wrote {lines_written} lines ({len(train_lines)} train, {len(validation_lines)} validation) to '{train_filepath}'.")
    holdout_after = len(train_lines)

    if include_unannotated:
        # want to write out a test file with the unannotated data
        lines = []
        for i in range(len(un_df)):
            journal = un_df.iloc[i]
            journal_text = get_cleaned_text_for_vw(journal['journal_text'])
            identifier = f"sid{journal['site_id']}joid{journal['journal_oid']}"
            # need to include all the labels in the test file in order to get predictions from them
            label_section = " ".join(resp_subset)
            formatted_line = f"{label_section} {identifier}|J {journal_text}\n"
            lines.append(formatted_line)
        random.shuffle(lines)
        lines_written = 0
        with open(test_filepath, 'w') as outfile:
            for formatted_line in lines:
                outfile.write(formatted_line)
                lines_written += 1
        print(f"Wrote {lines_written} lines to '{test_filepath}.'")  
    return train_filepath, test_filepath, holdout_after


def format_phase_df_as_multiclass(df, output_dir, validation_site_ids, identifier="default", include_unannotated=True):
    """

    :param df: DataFrame produced by phase.get_annotated_phase_df()
    :param output_dir: The directory in which generated training and testing files should be written.
    :param validation_site_ids: List of site_ids to include in the validation set
    :param identifier: A text identifier appended to the name of all generated files.
    :param include_unannotated: If unannotated entries in the given df should be included.
    :return: train_filepath, test_filepath, holdout_after
    """
    a_df = df[df.is_annotated]
    un_df = df[~df.is_annotated]
    assert len(a_df) + len(un_df) == len(df)

    train_filename = "phase_csoaa_" + identifier + ".train"
    test_filename = "phase_csoaa_" + identifier + ".test"

    train_filepath = os.path.join(output_dir, train_filename)
    test_filepath = os.path.join(output_dir, test_filename)

    # generate the lines to be written to the output file
    train_lines = []
    validation_lines = []
    for site_id, group in a_df.groupby(by='site_id', sort=False):
        for i in group.index:
            journal = group.loc[i]
            journal_oid = journal['journal_oid']
            identifier = "sid" + str(site_id) + "joid" + journal_oid

            label_section = ""
            for phase_label in phase_labels:
                phase_score = journal[phase_label + "_score"]
                vw_score = 1 - phase_score  # since CSOAA weights are inverted...
                label_section += f"{phase_label}:{vw_score} "

            journal_section = f"|J is_present:1 {get_cleaned_text_for_vw(journal.journal_text)}"
            if journal.journal_index >= 1:
                prev_journal = group[group.journal_index == journal.journal_index - 1].iloc[0]
                prev_journal_section = f"|J_prev is_present:1 {get_cleaned_text_for_vw(prev_journal.journal_text)}"
                # seconds_since_previous_journal:{journal.seconds_since_previous_journal}
            else:
                prev_journal = None
                prev_journal_section = "|J_prev is_present:0"
            if journal.journal_index >= 2:
                prev_prev_journal = group[group.journal_index == journal.journal_index - 1].iloc[0]
                prev_prev_journal_section = f"|J_prev_prev is_present:1 {get_cleaned_text_for_vw(prev_prev_journal.journal_text)}"
                # seconds_since_previous_journal:{prev_journal.seconds_since_previous_journal}
            else:
                prev_prev_journal_section = "|J_prev_prev is_present:0"
            feature_sections = f"{journal_section} {prev_journal_section} {prev_prev_journal_section}"

            formatted_line = label_section + identifier + feature_sections + "\n"
            if site_id in validation_site_ids:
                validation_lines.append(formatted_line)
            else:
                train_lines.append(formatted_line)
    # need to randomize the ordering of the training lines in the file
    random.shuffle(train_lines)
    # now, write the lines to a file
    lines_written = 0
    with open(train_filepath, 'w') as outfile:
        for formatted_line in train_lines:
            outfile.write(formatted_line)
            lines_written += 1
        for formatted_line in validation_lines:
            outfile.write(formatted_line)
            lines_written += 1
    print(f"Wrote {lines_written} lines ({len(train_lines)} train, {len(validation_lines)} validation) to '{train_filepath}'.")
    holdout_after = len(train_lines)

    if include_unannotated:
        # want to write out a test file with the unannotated data
        lines = []
        for site_id, group in un_df.groupby(by='site_id'):
            for i in group.index:
                journal = group.loc[i]
                journal_oid = journal['journal_oid']
                identifier = "sid" + str(site_id) + "joid" + journal_oid
                label_section = " ".join(phase_labels) + " "
                journal_section = f"|J is_present:1 {get_cleaned_text_for_vw(journal.journal_text)}"
                if journal.journal_index >= 1:
                    prev_journal = group[group.journal_index == journal.journal_index - 1].iloc[0]
                    prev_journal_section = f"|J_prev is_present:1 seconds_since_previous_journal:{journal.seconds_since_previous_journal} {get_cleaned_text_for_vw(prev_journal.journal_text)}"
                else:
                    prev_journal = None
                    prev_journal_section = "|J_prev is_present:0"
                if journal.journal_index >= 2:
                    prev_prev_journal = group[group.journal_index == journal.journal_index - 1].iloc[0]
                    prev_prev_journal_section = f"|J_prev_prev is_present:1 seconds_since_previous_journal:{prev_journal.seconds_since_previous_journal} {get_cleaned_text_for_vw(prev_prev_journal.journal_text)}"
                else:
                    prev_prev_journal_section = "|J_prev_prev is_present:0"
                feature_sections = f"{journal_section} {prev_journal_section} {prev_prev_journal_section}"

                formatted_line = label_section + identifier + feature_sections + "\n"
                lines.append(formatted_line)
        lines_written = 0
        with open(test_filepath, 'w') as outfile:
            for formatted_line in lines:
                outfile.write(formatted_line)
                lines_written += 1
        print(f"Wrote {lines_written} lines to '{test_filepath}.'")
    return train_filepath, test_filepath, holdout_after


def read_raw_binary_responsibility_preds(raw_pred_filepath):
    with open(raw_pred_filepath, 'r') as infile:
        raw_pred_lines = infile.readlines()

    predictions = []
    for line in raw_pred_lines:
        tokens = line.split()
        identifier = tokens[-1]
        site_id, journal_oid = identifier.split("joid")
        site_id = int(site_id[3:])

        prediction = {"site_id": site_id,
                      "journal_oid": journal_oid}
        preds = tokens[:-1]
        assert len(preds) == 1
        pred_str = preds[0]
        raw_pred_str = pred_str
        raw_pred = float(raw_pred_str)
        if not np.isfinite(raw_pred):
            print("WARNING:", raw_pred_str)
        prediction["raw_pred"] = raw_pred
        predictions.append(prediction)
    df = pd.DataFrame(predictions)
    return df


def read_raw_multiclass_phase_preds(raw_pred_filepath):
    """
    Reads a VW prediction set made from a training/testing file produced by the
    format_phase_df_as_multiclass function.

    :param raw_pred_filepath: Filepath of the VW predictions
    :return: pandas DataFrame with fields for each of the phases, ending in _pred
    """
    with open(raw_pred_filepath, 'r') as infile:
        raw_pred_lines = infile.readlines()

    predictions = []
    for line in raw_pred_lines:
        tokens = line.split()
        identifier = tokens[-1]
        site_id, journal_oid = identifier.split("joid")
        site_id = int(site_id[3:])

        prediction = {"site_id": site_id,
                      "journal_oid": journal_oid}
        preds = tokens[:-1]
        for i, pred_str in enumerate(preds):
            num, raw_pred_str = pred_str.split(":")
            assert int(num) == i + 1
            resp = phase_labels[i]
            raw_pred = float(raw_pred_str)
            if not np.isfinite(raw_pred):
                print("WARNING:", raw_pred_str)
            prediction[resp + "_pred"] = raw_pred

        predictions.append(prediction)
    df = pd.DataFrame(predictions)
    return df


def read_raw_multiclass_responsibility_preds(raw_pred_filepath, resp_subset=responsibility_labels):
    """
    Reads a VW prediction set made from a training/testing file produced by the
    format_responsibility_df_as_multiclass function.
    
    :param raw_pred_filepath: Filepath of the VW predictions
    :return: pandas DataFrame with fields for each of the responsibilities, ending in _pred
    """
    with open(raw_pred_filepath, 'r') as infile:
        raw_pred_lines = infile.readlines()

    predictions = []
    for line in raw_pred_lines:
        tokens = line.split()
        identifier = tokens[-1]
        site_id, journal_oid = identifier.split("joid")
        site_id = int(site_id[3:])

        prediction = {"site_id": site_id,
                      "journal_oid": journal_oid}
        preds = tokens[:-1]
        for i, pred_str in enumerate(preds):
            num, raw_pred_str = pred_str.split(":")
            assert int(num) == i + 1
            resp = resp_subset[i]
            raw_pred = float(raw_pred_str)
            if not np.isfinite(raw_pred):
                print("WARNING:", raw_pred_str)
            prediction[resp + "_pred"] = raw_pred

        predictions.append(prediction)
    df = pd.DataFrame(predictions)
    return df


def get_responsibility_named_labels(resp_subset=responsibility_labels):
    """

    :return: to be passed to the model training like so: --named_labels {}
    """
    return ",".join(resp_subset)


def get_phase_named_labels():
    """

    :return: to be passed to the model training like so: --named_labels {}
    """
    return ",".join(phase_labels)
