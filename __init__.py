from typing import Dict
from aqt import mw
from aqt.utils import showInfo, qconnect
from aqt.qt import *
import json
import os
from inspect import getsourcefile
import sys
import threading
import pickle

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
from ahocorapy.keywordtree import KeywordTree

addon_directory = os.path.dirname(__file__)

hsk_data = None
hsk_tree = None
freq_for_word = None
freq_tree = None
def load_data():
    global hsk_data
    global hsk_tree
    global freq_tree
    global freq_for_word

    hsk_file_path = os.path.join(addon_directory, 'hsk.json')
    hsk_file = open(hsk_file_path, encoding='utf_8_sig')
    hsk_data = json.load(hsk_file)

    hsk_tree_file_path = os.path.join(addon_directory, 'hsk_tree.pickle')
    hsk_tree_file = open(hsk_tree_file_path, 'rb')
    hsk_tree = pickle.load(hsk_tree_file)
    hsk_tree_file.close()

    freq_file_path = os.path.join(addon_directory, 'freq.txt')
    freq_file = open(freq_file_path, encoding='utf_8_sig')
    freq_data = freq_file.read().splitlines()
    freq_for_word = {k: v for v, k in enumerate(freq_data)}

    freq_tree_file_path = os.path.join(addon_directory, 'freq_tree.pickle')
    freq_tree_file = open(freq_tree_file_path, 'rb')
    freq_tree = pickle.load(freq_tree_file)
    freq_tree_file.close()

def freq_num_stars(freq: int) -> int:
    if freq <= 1500:
        return 5
    elif freq <= 5000:
        return 4
    elif freq <= 15000:
        return 3
    elif freq <= 30000:
        return 2
    elif freq <= 60000:
        return 1
    else:
        return 0

def num_words_for_stars(num_stars: int) -> int:
    return [ -1, 30000, 15000, 10000, 3500, 1500 ][num_stars]

def num_words_in_hsk_level(hsk_level: int) -> int:
    return [ 150, 150, 300, 600, 1300, 2500 ][hsk_level - 1]

def chinese_stats() -> None:
    # Extract the sentences from the notes
    col = mw.col
    sentences = list()
    note_ids = col.find_notes('')
    for note_id in note_ids:
        note = col.getNote(note_id)
        if 'Expression' not in note:
            continue
        expression = note['Expression']
        sentences.append(expression)

    # Wait on data loading to finish
    load_data_thread.join()

    # Search the sentences for HSK words
    hsk_found_words = set()
    hsk_results = dict()
    for hsk_level in range(1, 7):
        hsk_results.setdefault(str(hsk_level), 0)

    for sentence in sentences:
        for word, _ in hsk_tree.search_all(sentence):
            if word in hsk_found_words:
                continue
            hsk_level = hsk_data[word]
            hsk_results[str(hsk_level)] += 1
            hsk_found_words.add(word)

    # Search the sentences for words in the frequency list
    freq_found_words = set()
    freq_results = dict()
    for num_stars in range(0, 6):
        freq_results.setdefault(str(num_stars), 0)

    for sentence in sentences:
        for word, _ in freq_tree.search_all(sentence):
            if word in freq_found_words:
                continue
            freq = freq_for_word[word]
            num_stars = freq_num_stars(freq)
            freq_results[str(num_stars)] += 1
            freq_found_words.add(word)

    # Create output summary
    strs = []

    strs.append("HSK Stats")
    for level_str, num_found in sorted(hsk_results.items()):
        percent_known_words  = round(num_found / num_words_in_hsk_level(int(level_str)) * 100.0, 1)
        strs.append('HSK {}: {} known words ({}%)'.format(level_str, num_found, percent_known_words))

    strs.append("\nFrequency Stats")
    for num_stars_str, num_found in sorted(freq_results.items(), reverse=True):
        num_stars = int(num_stars_str)
        num_hollow_stars = 5 - num_stars
        stars_str = num_stars * '★' + "☆" * num_hollow_stars
        star_total_num_words = num_words_for_stars(num_stars)
        percent_known_words = round(float(num_found) / float(star_total_num_words) * 100.0, 1)
        percent_known_str = "N/A" if num_stars == 0 else (str(percent_known_words) + '%')
        strs.append('{}: {} known words ({})'.format(stars_str, num_found, percent_known_str))

    output = '\n'.join(strs)

    showInfo(output)

action = QAction("Chinese Stats", mw)
qconnect(action.triggered, chinese_stats)
mw.form.menuTools.addAction(action)

# Kick off loading the data since it takes a couple seconds.
load_data_thread = threading.Thread(target=load_data)
load_data_thread.start()