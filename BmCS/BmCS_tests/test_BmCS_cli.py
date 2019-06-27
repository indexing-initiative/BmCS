import argparse
import sys
import json
import datetime
from pkg_resources import resource_string
import unittest
from unittest.mock import patch

from ..combined_model import *
from ..daily_update_file_parser import parse_update_file
from ..preprocess_CNN_data import get_batch_data 
from ..preprocess_voting_data import preprocess_data
from ..BmCS_tests.BmCS_test import BmCS_test_main
from BmCS import BmCS

class test_BmCS_cli(unittest.TestCase):
    """
    Class to test 
    the effect of command line arguments on input to models
    Primarily this is to make sure journal dropping things 
    in the daily_update_parser work as expected,
    especially as more things are added on
    """

    def test_main(self):
        """
        Main function to run voting and CNN, combine results,
        adjust decision threshold, and make predictions
        """

        # Use unitttest.mock.patch to simulate command line arguments, so that they can be used 
        # with pytest
        # https://stackoverflow.com/questions/18160078/how-do-you-write-tests-for-the-argparse-portion-of-a-python-module
        with patch("argparse.ArgumentParser.parse_args", return_value=argparse.Namespace(
                                path="null",
                                group_thresh=False,
                                journal_drop=True,
                                pub_type_filter=True,
                                destination=".",
                                validation=False,
                                test=False,
                                predict_medline=False,
                                predict_all=False
                                )):
            args = BmCS.get_args().parse_args()

        journal_ids_path = resource_filename(__name__, "../models/journal_ids.txt")
        word_indicies_path = resource_filename(__name__, "../models/word_indices.txt")
        
        selectively_indexed_id_path = resource_filename(__name__, "../selectively_indexed_id_mapping.json")
        with open(selectively_indexed_id_path, "r") as f:
            selectively_indexed_ids = json.load(f)
     
        group_id_path = resource_filename(__name__, "../group_ids.json") 
        with open(group_id_path, "r") as f:
            group_ids = json.load(f)

        group_thresh = args.group_thresh
        journal_drop = args.journal_drop
        destination = args.destination
        predict_medline = args.predict_medline
        predict_all = args.predict_all
        pub_type_filter = args.pub_type_filter

        # Ids of citations in test_citations.xml.
        # The ids have been hand selected, for their status and indexing status,
        # so that their treatment by the system can be predicted.
        # 30160246 is included in the test_citations as an example of something with PubMed-not-MEDLINE
        # from selectively indexed journal. Useful to know, but not used in tests below.
        test_ids = [
                "12269810", # MEDLINE status, from non-selectively indexed journal
                "21179314", # PubMed-not-MEDLINE status, from non-selectively indexed journals
                "30886396", # In process status, from selectively indexed journal, system is very confident, i.e., will be marked for automatic indexing
                "29994383", # In process status, from selectively indexed journal in journal drop list
                "30883917", # Has pubtype indicator in title. In process status, fully indexed journal. 
                "30299937", # Has pubtype indicator in title. In process status, selectively indexed journal.
                ]
                    
        XML_path = resource_filename(__name__, "datasets/test_citations.xml")
        self.assertEqual(journal_drop, True)
        self.assertEqual(predict_medline, False)
        # Run on citations curated for testing command line options
        # All dropping options are considered in parse_update_file
        # First run with default, where journal_drop == True and predict_medline == False
        citations = parse_update_file(
                XML_path, journal_drop, predict_medline, 
                selectively_indexed_ids, predict_all
                )
	# There should be two citations from selectively indexed journals with in process status: 30299937 and 30886396
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0]['pmid'], int(test_ids[2]))
        self.assertEqual(citations[1]['pmid'], int(test_ids[5]))

        # Then set journal drop to false:
        journal_drop = not journal_drop
        citations = parse_update_file(XML_path, journal_drop, predict_medline, selectively_indexed_ids, predict_all)
        self.assertEqual(len(citations), 3)
        self.assertEqual(citations[0]['pmid'], int(test_ids[3]))
        self.assertEqual(citations[1]['pmid'], int(test_ids[2]))
        
        # And then try with predict_medline as true. 
        predict_medline = not predict_medline
        citations = parse_update_file(XML_path, journal_drop, predict_medline, selectively_indexed_ids, predict_all)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]['pmid'], int(test_ids[0]))
        
        # Finally test with predict all, and use those citations for the rest of the tests.
        predict_all = not predict_all
        citations = parse_update_file(XML_path, journal_drop, predict_medline, selectively_indexed_ids, predict_all)
        self.assertEqual(len(citations), 7, [citation['pmid'] for citation in citations])

        # Test length and type of data + predictions
        voting_citations, journal_ids, pmids = preprocess_data(citations)
        self.assertIsInstance(voting_citations, dict)
        for key in voting_citations:
            self.assertIsInstance(voting_citations[key], list)
        voting_predictions = run_voting(voting_citations)
        self.assertEqual(len(voting_predictions), len(citations))
        CNN_citations = get_batch_data(citations, journal_ids_path, word_indicies_path)
        self.assertIsInstance(CNN_citations, dict)
        for key in CNN_citations:
            if key == "pmids":
                self.assertIsInstance(CNN_citations[key], list)
            else:
                self.assertIsInstance(CNN_citations[key], np.ndarray)
        cnn_predictions = run_CNN(CNN_citations)
        self.assertEqual(len(cnn_predictions), len(citations))
        combined_predictions = combine_predictions(voting_predictions, cnn_predictions)
        self.assertEqual(len(combined_predictions), len(citations))
        prediction_dict = {'predictions': combined_predictions, 'journal_ids': journal_ids}
        self.assertEqual(len(prediction_dict['predictions']), len(prediction_dict['journal_ids']))
        adjusted_predictions = adjust_thresholds(prediction_dict, group_ids, group_thresh) 
        self.assertEqual(len(combined_predictions), len(adjusted_predictions))

        # Test pubtype filter
        # The labels start as 1s
        self.assertEqual(adjusted_predictions[5], 1) 
        self.assertEqual(adjusted_predictions[6], 1) 
        adjusted_predictions = filter_pub_type(citations, adjusted_predictions)
        self.assertEqual(adjusted_predictions[5], 2) 
        self.assertEqual(adjusted_predictions[6], 2) 
        
        # Test adjustment of very confident predictions
        adjusted_predictions = adjust_in_scope_predictions(adjusted_predictions, prediction_dict)
        self.assertEqual(adjusted_predictions[4], 3) 
