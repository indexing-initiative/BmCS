import argparse
import json
import datetime
from pkg_resources import resource_string

from .combined_model import *
from .daily_update_file_parser import parse_update_file
from .preprocess_CNN_data import get_batch_data 
from .preprocess_voting_data import preprocess_data
from .BmCS_tests.BmCS_test import BmCS_test_main


def get_args():
    """
    Get command line parser
    """

    parser = argparse.ArgumentParser(description="Arguments for initializing classifier")
    parser.add_argument("--path",
                        dest="path",
                        help="Path to XML containing batch of citations")
    parser.add_argument("--group-thresh",
                        dest="group_thresh",
                        action="store_true",
                        help="If included, use predetermined threshold for science and jurisprudence groups. Default is to not use these group thresholds, as they have been shown hard to predict.")
    parser.add_argument("--no-journal-drop",
                        dest="journal_drop",
                        action="store_false",
                        help="If included, model will make predictions for misindexed journals that have been shown to be difficult to classify")
    parser.add_argument("--no-pubtype-filter",
                        dest="pub_type_filter",
                        action="store_false",
                        help="If included, turn off the prediction adjustment for pub types. This means predictions will be made for comments, erratum, etc. By default, this is on.")
    parser.add_argument("--dest",
                        dest="destination",
                        default="./",
                        help="Destination directory for predictions or testing metrics. Will default to the current directory")
    parser.add_argument("--validation",
                        dest="validation",
                        action="store_true",
                        help="If included, test the system on the validation dataset. Will output metrics to BmCS_test_results.txt")
    parser.add_argument("--test",
                        dest="test",
                        action="store_true",
                        help="If included, test the system on the test dataset. Will output metrics to BmCS_test_results.txt")
    parser.add_argument("--predict-medline",
                        dest="predict_medline",
                        action="store_true",
                        help="If included, the system will make predictions for not selectively indexed citations that are labeled MEDLINE.  If not included, it will only make predictions for citations from selectively indexed journals that have been suggested to be important")
    parser.add_argument("--predict-all",
                        dest="predict_all",
                        action="store_true",
                        help="If included, the system will make predictions for all citations in the xml file, regardless of status or selective indexing status.")
    return parser


def save_predictions(adjusted_predictions, prediction_dict, pmids, destination):
    """
    Save predictions to file in format
    pmid|binary prediction|probability|journal
    """
    
    with open("{0}citation_predictions_{1}.txt".format(destination, datetime.datetime.today().strftime('%Y-%m-%d')), "w") as f:
        for i, prediction in enumerate(adjusted_predictions):
            f.write("{0}|{1}|{2}|{3}\n".format(
                pmids[i], 
                prediction, 
                prediction_dict['predictions'][i], 
                prediction_dict['journal_ids'][i]
                ))


def main():
    """
    Main function to run ensemble and CNN, combine results,
    adjust decision threshold, and make predictions
    """

    args = get_args().parse_args()
    journal_ids_path = resource_filename(__name__, "models/journal_ids.txt")
    word_indices_path = resource_filename(__name__, "models/word_indices.txt")
    
    selectively_indexed_id_path = resource_filename(__name__, "selectively_indexed_id_mapping.json")
    with open(selectively_indexed_id_path, "r") as f:
        selectively_indexed_ids = json.load(f)
 
    group_id_path = resource_filename(__name__, "group_ids.json") 
    with open(group_id_path, "r") as f:
        group_ids = json.load(f)

    group_thresh = args.group_thresh
    journal_drop = args.journal_drop
    pub_type_filter = args.pub_type_filter
    destination = args.destination
    predict_medline = args.predict_medline
    predict_all = args.predict_all

    # Run system on test or validation set if specified
    # Predict MEDLINE has no effect
    if args.test or args.validation:
        dataset = "test" if args.test else "validation"
        BmCS_test_main(
            dataset, journal_ids_path, word_indices_path, 
            group_thresh, journal_drop, destination, group_ids, args)

    #Otherwise run on batch of citations
    else:
        XML_path = args.path
        # All dropping options are considered in parse_update_file
        citations = parse_update_file(
                XML_path, journal_drop, predict_medline, 
                selectively_indexed_ids, predict_all
                ) 
        voting_citations, journal_ids, pmids = preprocess_data(citations)
        voting_predictions = run_voting(voting_citations)
        CNN_citations = get_batch_data(citations, journal_ids_path, word_indices_path)
        cnn_predictions = run_CNN(CNN_citations)
        combined_predictions = combine_predictions(voting_predictions, cnn_predictions)
        prediction_dict = {'predictions': combined_predictions, 'journal_ids': journal_ids}
        adjusted_predictions = adjust_thresholds(prediction_dict, group_ids, group_thresh) 
        # Convert predictions for pub types based on string matching rules in title 
        # and PublicationType rules
        if pub_type_filter:
            adjusted_predictions = filter_pub_type(citations, adjusted_predictions)
        # Mark citations for automatic selection if above prediction threshold
        adjusted_predictions = adjust_in_scope_predictions(adjusted_predictions, prediction_dict)
        save_predictions(adjusted_predictions, prediction_dict, pmids, destination)
