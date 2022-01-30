from aqt import mw
from aqt.utils import qconnect
from aqt.qt import *
from aqt.webview import AnkiWebView
import json
import os
import threading
import pickle
import datetime
from .config import *
from .lib.gviz import gviz_api

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
    config = load_search_field_config()
    sentence_note_ids = list()
    sentence_for_note_id = dict()
    note_info = {}

    for note_id, model_id, deck_id, first_study_date in mw.col.db.execute("select nid, mid, did, min(revlog.id) as date from notes, cards, revlog where notes.id=cards.nid and cards.id=revlog.cid and cards.queue>0 group by notes.id order by date"):
        search_field = selected_field_from_config(config, str(deck_id), str(model_id))
        # Skip this note if the associated search field was not specified in the config.
        if search_field is None:
            continue
        # Skip this note if the associated search field no longer exists in the note.
        note = mw.col.getNote(note_id)
        if search_field not in note:
            continue
        sentence_note_ids.append(note_id)
        sentence_for_note_id[note_id] = note[search_field]
        note_info[note_id] = first_study_date

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
    for num_stars in reversed(range(0, 6)):
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

    return (note_info, hsk_results, freq_results)

def to_day(time: datetime):
    return datetime.datetime.strftime(time, '%Y-%m-%d')

def to_datetime(time_str: str):
    return datetime.datetime.strptime(time_str, '%Y-%m-%d')

def results_by_day(note_info, results):
    results_by_date = dict()
    for key, note_ids in results.items():
        for note_id in note_ids:
            created_epoch = int(note_info[note_id]) / 1000.0
            time_note_created = datetime.datetime.fromtimestamp(created_epoch)
            date_note_created_str = to_day(time_note_created)

            if not date_note_created_str in results_by_date:
                results_by_date[date_note_created_str] = dict()

            if not key in results_by_date[date_note_created_str]:
                results_by_date[date_note_created_str][key] = 0

            results_by_date[date_note_created_str][key] += 1
    return results_by_date
    
def cumulative_results_by_day(note_info, results):
    results_by_date = results_by_day(note_info, results)
    cumulative_results = dict()
    running_total = dict.fromkeys(results.keys(), 0)
    for date_str in sorted(results_by_date):
        results = results_by_date[date_str]
        for key, num_words_created in results.items():
            running_total[key] += num_words_created
        cumulative_results[date_str] = dict(running_total)
    return cumulative_results

def chart_json(note_info, results, column_name_func):
    cumulative_daily_results = cumulative_results_by_day(note_info, results)

    column_ids = dict()
    for key in results.keys():
        column_ids[key] = "col{}".format(key)
            
    # Generate per-day chart data
    data = []
    for date_str, cum_results in cumulative_daily_results.items():
        row = { "date": to_datetime(date_str) }
        for key, num_words_created in cum_results.items():
            column_id = column_ids[key]
            row[column_id] = num_words_created
        data.append(row)

    description = {
        "date": ("date", "Date")
    }
    for key in column_ids:
        column_id = column_ids[key]
        description[column_id] = ("number", column_name_func(key))
            
    data_table = gviz_api.DataTable(description)
    data_table.LoadData(data)
    return data_table.ToJSon(
        columns_order=tuple(["date"]) + tuple(column_ids.values()),
        order_by="date"
    )

class MyWebView(AnkiWebView):
    def __init__(self):
        AnkiWebView.__init__(self, None)
        page_template = """
        <html>
        <script src="https://www.gstatic.com/charts/loader.js"></script>
        <script>
            google.charts.load('current', {packages:['corechart']});
            google.charts.setOnLoadCallback(drawCharts);

            function drawHskChart() {
                var options = {
                    isStacked: true,
                    focusTarget: 'category',
                    title: 'Known Words by HSK Level',
                    hAxis: {title: 'Date',  titleTextStyle: {color: '#333'}},
                    vAxis: {minValue: 0}
                };
                var chart = new google.visualization.AreaChart(document.getElementById('hsk_chart'));
                var data = new google.visualization.DataTable(%s, 0.6);
                chart.draw(data, options);
            }

            function drawFreqChart() {
                var options = {
                    isStacked: true,
                    focusTarget: 'category',
                    title: 'Known Words by Frequency Rating',
                    hAxis: {title: 'Date',  titleTextStyle: {color: '#333'}},
                    vAxis: {minValue: 0}
                };
                var chart = new google.visualization.AreaChart(document.getElementById('freq_chart'));
                var data = new google.visualization.DataTable(%s, 0.6);
                chart.draw(data, options);
            }

            function drawCharts() {
                drawHskChart();
                drawFreqChart();
            }

            $(window).resize(function() {
                drawCharts()
            });
        </script>
        <body>
            <H1>Chinese Stats</H1>
            <div id="hsk_chart" style="height: 500px; width: 100%%"></div>
            <div id="freq_chart" style="height: 500px; width: 100%%"></div>
        </body>
        </html>
        """

        # Create the chart data
        note_info, hsk_results, freq_results = chinese_stats()

        def hsk_column_name(column_id):
            return "HSK {}".format(column_id)
        hsk_json = chart_json(note_info, hsk_results, hsk_column_name)

        def freq_column_name(column_id):
            num_stars = int(column_id)
            num_hollow_stars = 5 - num_stars
            return num_stars * '★' + "☆" * num_hollow_stars
        freq_json = chart_json(note_info, freq_results, freq_column_name)

        # Inject it into the template
        html = page_template % (hsk_json, freq_json)
        self.stdHtml(html)

def show_webview():
    webview = MyWebView()
    webview.show()
    webview.setFocus()
    webview.activateWindow()

stats_action = QAction("Chinese Stats (Stats)", mw)
qconnect(stats_action.triggered, show_webview)
mw.form.menuTools.addAction(stats_action)

settings_action = QAction("Chinese Stats (Settings)", mw)
qconnect(settings_action.triggered, config.show_settings)
mw.form.menuTools.addAction(settings_action)

# Kick off loading the data since it takes a couple seconds.
load_data_thread = threading.Thread(target=load_data)
load_data_thread.start()