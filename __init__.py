from typing import Dict
from aqt import mw
from aqt.utils import showInfo, qconnect
from aqt.qt import *
from aqt.webview import AnkiWebView
import json
import os
from inspect import getsourcefile
import sys
import threading
import pickle
import datetime
import itertools

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
from ahocorapy.keywordtree import KeywordTree
from gviz import gviz_api

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
    sentence_note_ids = list()
    note_ids = col.find_notes('')
    sentence_for_note_id = dict()

    for note_id in note_ids:
        note = col.getNote(note_id)
        if 'Expression' not in note:
            continue
        sentence_note_ids.append(note_id)
        sentence_for_note_id[note_id] = note['Expression']

    sentence_note_ids.sort()

    # Wait on data loading to finish
    load_data_thread.join()

    # Search the sentences for HSK words
    hsk_found_words = set()
    hsk_results = dict()
    for hsk_level in range(1, 7):
        hsk_results.setdefault(str(hsk_level), [])

    for note_id in sentence_note_ids:
        sentence = sentence_for_note_id[note_id]
        for word, _ in hsk_tree.search_all(sentence):
            if word in hsk_found_words:
                continue
            hsk_level = hsk_data[word]
            hsk_results[str(hsk_level)].append(note_id)
            hsk_found_words.add(word)

    # Search the sentences for words in the frequency list
    freq_found_words = set()
    freq_results = dict()
    for num_stars in range(0, 6):
        freq_results.setdefault(str(num_stars), [])

    for note_id in sentence_note_ids:
        sentence = sentence_for_note_id[note_id]
        for word, _ in freq_tree.search_all(sentence):
            if word in freq_found_words:
                continue
            freq = freq_for_word[word]
            num_stars = freq_num_stars(freq)
            freq_results[str(num_stars)].append(note_id)
            freq_found_words.add(word)

    return (hsk_results, freq_results)

def to_day(time: datetime):
    return datetime.datetime.strftime(time, '%Y-%m-%d')

def to_datetime(time_str: str):
    return datetime.datetime.strptime(time_str, '%Y-%m-%d')


class MyWebView(AnkiWebView):
    def __init__(self):
        AnkiWebView.__init__(self, None)
        page_template = """
        <html>
        <script src="https://www.gstatic.com/charts/loader.js"></script>
        <script>
            google.charts.load('current', {packages:['corechart']});
            google.charts.setOnLoadCallback(drawChart);
            
            var options = {
                isStacked: true,
                title: 'Known HSK Words',
                hAxis: {title: 'Date',  titleTextStyle: {color: '#333'}},
                vAxis: {minValue: 0}
            };

            function drawChart() {
                var chart = new google.visualization.AreaChart(document.getElementById('hsk_chart'));
                var data = new google.visualization.DataTable(%(json)s, 0.6);
                chart.draw(data, options);
            }

            $(window).resize(function(){
                drawChart();
            });
        </script>
        <body>
            <H1>Known HSK Words</H1>
            <div id="hsk_chart" style="height: 500px; width: 100%%"></div>
        </body>
        </html>
        """

        # Creating the data
        hsk_results, freq_results = chinese_stats()

        # Group results by day
        hsk_results_by_date = dict()
        for hsk_level, note_ids in hsk_results.items():
            for note_id in note_ids:
                # Group results by day        
                time_note_created = datetime.datetime.fromtimestamp(int(note_id) / 1000.0)
                date_note_created_str = to_day(time_note_created)

                if not date_note_created_str in hsk_results_by_date:
                    hsk_results_by_date[date_note_created_str] = dict()

                if not hsk_level in hsk_results_by_date[date_note_created_str]:
                    hsk_results_by_date[date_note_created_str][hsk_level] = 0

                hsk_results_by_date[date_note_created_str][hsk_level] += 1
        
        # Generate cumulative results per day
        hsk_results_cum = dict()
        hsk_level_running_totals = { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 , '6': 0 }
        for date_str in sorted(hsk_results_by_date):
            results = hsk_results_by_date[date_str]
            for hsk_level, num_words_created in results.items():
                hsk_level_running_totals[hsk_level] += num_words_created
            hsk_results_cum[date_str] = dict(hsk_level_running_totals)
                
        # Generate per-day chart data
        data = []
        for date_str, results in hsk_results_cum.items():
            row = { "date": to_datetime(date_str) }
            for hsk_level, num_words_created in results.items():
                row["hsk{}".format(hsk_level)] = num_words_created
            data.append(row)

        description = {
            "date": ("date", "Date"),
            "hsk1": ("number", "HSK 1"),
            "hsk2": ("number", "HSK 2"),
            "hsk3": ("number", "HSK 3"),
            "hsk4": ("number", "HSK 4"),
            "hsk5": ("number", "HSK 5"),
            "hsk6": ("number", "HSK 6"),
        }
                
        # Loading it into gviz_api.DataTable
        data_table = gviz_api.DataTable(description)
        data_table.LoadData(data)

        # Create a JSON string.
        json = data_table.ToJSon(columns_order=("date", "hsk1", "hsk2", "hsk3", "hsk4", "hsk5", "hsk6"),
                                order_by="date")
        html = page_template % vars()
        self.stdHtml(html)

def show_webview():
    webview = MyWebView()
    webview.show()
    webview.setFocus()
    webview.activateWindow()

action = QAction("Chinese Stats", mw)
qconnect(action.triggered, show_webview)
mw.form.menuTools.addAction(action)

# Kick off loading the data since it takes a couple seconds.
load_data_thread = threading.Thread(target=load_data)
load_data_thread.start()