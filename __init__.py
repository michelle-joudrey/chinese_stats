from typing import Dict
from aqt import mw
from aqt.utils import showInfo, qconnect
from aqt.qt import *
import json
import re
import os
from anki.exporting import Exporter
from inspect import getsourcefile
import sys
import time
import pickle

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
from ahocorapy.keywordtree import KeywordTree

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

def chinese_stats() -> None:
    addon_directory = os.path.dirname(__file__)
    col = mw.col
    exporter = Exporter(col)
    decks = col.decks
    sentences = list()

    # Extract the sentences from the notes
    for deck_name_and_id in decks.all_names_and_ids():
        deck_id = deck_name_and_id.id
        card_ids = decks.cids(deck_id)
        for card_id in card_ids:
            card = col.getCard(card_id)
            note = card.note()
            try: 
                expression = note['Expression']
            except KeyError:
                continue
            # Remove html from the sentence
            sentence = exporter.stripHTML(expression)
            # Remove pinyin in the sentence e.g. "[ni3 hao3]" in "你好[ni3 hao3]"
            sentence = re.sub('\[.*?\]', '', sentence)
            sentences.append(sentence)

    # Search the sentences for HSK words
    hsk_file_path = os.path.join(addon_directory, 'hsk.json')
    hsk_file = open(hsk_file_path, encoding='utf_8_sig')
    hsk_data = json.load(hsk_file)
    hsk_found_words = set()
    hsk_results = dict()
    for hsk_level in range(1, 7):
        hsk_results.setdefault(str(hsk_level), 0)

    for sentence in sentences:
        for word, hsk_level in hsk_data.items():
            if word in hsk_found_words:
                continue
            if word in sentence:
                hsk_results[str(hsk_level)] += 1
                hsk_found_words.add(word)

    # Search the sentences for words in the frequency list
    freq_file_path = os.path.join(addon_directory, 'freq.txt')
    freq_file = open(freq_file_path, encoding='utf_8_sig')
    freq_data = freq_file.read().splitlines()
    freq_for_word = {k: v for v, k in enumerate(freq_data)}

    kwtree_file_path = os.path.join(addon_directory, 'freq-aho.pickle')
    kwtree_file = open(kwtree_file_path, 'rb')
    kwtree = pickle.load(kwtree_file)
    kwtree_file.close()
    
    freq_found_words = set()
    freq_results = dict()
    for num_stars in range(0, 6):
        freq_results.setdefault(str(num_stars), 0)

    # for each word in the frequency list, find out if it is within the list of sentences.
    all_sentences = ''.join(sentences)
    matches = kwtree.search_all(all_sentences)
    for word, index in matches:
        if word in freq_found_words:
            continue
        freq = freq_for_word[word]
        num_stars = freq_num_stars(freq)
        freq_results[str(num_stars)] += 1
        freq_found_words.add(word)

    # Create output summary
    strs = []

    strs.append("HSK Stats")
    for level, num_found in sorted(hsk_results.items()):
        strs.append('HSK {}: {} known'.format(level, num_found))

    strs.append("\nFrequency Stats")
    for num_stars, num_found in sorted(freq_results.items(), reverse=True):
        num_hollow_stars = 5 - int(num_stars)
        stars_str = int(num_stars) * '★' + "☆" * num_hollow_stars
        strs.append('{}: {} known'.format(stars_str, num_found))

    output = '\n'.join(strs)

    showInfo(output)

action = QAction("Chinese Stats", mw)
qconnect(action.triggered, chinese_stats)
mw.form.menuTools.addAction(action)