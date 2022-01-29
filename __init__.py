import dataclasses
import functools
from aqt import mw
from aqt.utils import qconnect
from aqt.utils import tooltip
from aqt.qt import *
from aqt.webview import AnkiWebView
import json
import os
import sys
import threading
import pickle
import datetime
from typing import Optional
from typing import List
from dataclasses import dataclass

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
from ahocorapy.keywordtree import KeywordTree
from gviz import gviz_api
from dacite import from_dict

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
    sentence_for_note_id = dict()
    note_info = {}

    for note_id, first_study_date in col.db.execute("select nid, min(revlog.id) as date from notes, cards, revlog where notes.id=cards.nid and cards.id=revlog.cid and cards.queue>0 group by notes.id order by date;"):
        note = col.getNote(note_id)
        if 'Expression' not in note:
            continue
        sentence_note_ids.append(note_id)
        sentence_for_note_id[note_id] = note['Expression']
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

@dataclass
class SearchFieldConfigModel():
    id: str
    selected_field: str

@dataclass
class SearchFieldConfigDeck():
    id: str
    models: List[SearchFieldConfigModel]

@dataclass
class SearchFieldConfig():
    decks: List[SearchFieldConfigDeck]

def selected_field_from_config(config: SearchFieldConfig, deck_id: str, model_id: str) -> Optional[str]:
    for deck in config.decks:
        if deck.id == deck_id:
            for model in deck.models:
                if model.id == model_id:
                    return model.selected_field    

@dataclass
class SearchFieldConfigModelViewModel:
    name: str
    id: str
    fields: List[str]
    selected_field: Optional[str]

@dataclass
class SearchFieldConfigDeckViewModel:
    name: str
    id: str
    models: List[SearchFieldConfigModelViewModel]

@dataclass
class SearchFieldConfigViewModel:
    decks: List[SearchFieldConfigDeckViewModel]

def search_fields_config_view_model(config: SearchFieldConfigModel) -> SearchFieldConfigViewModel:
    decks: List[SearchFieldConfigDeckViewModel] = []

    for row in mw.col.db.execute('select group_concat(distinct notes.mid), cards.did from notes, cards where notes.id=cards.nid group by cards.did'):
        model_ids = row[0].split(',')
        deck_id = str(row[1])

        models: List[SearchFieldConfigModelViewModel] = []
        for model_id in model_ids:
            model = mw.col.models.get(model_id)
            model_name = model['name']

            fields: List[str] = []
            for field in model['flds']:
                fields.append(field['name'])

            selected_field = selected_field_from_config(config, deck_id, model_id)
            models.append(SearchFieldConfigModelViewModel(model_name, model_id, fields, selected_field))
    
        deck_name = mw.col.decks.get(deck_id)['name']
        decks.append(SearchFieldConfigDeckViewModel(deck_name, deck_id, models))

    return SearchFieldConfigViewModel(decks)

def search_fields_config(view_model: SearchFieldConfigViewModel) -> SearchFieldConfig:
    decks : List[SearchFieldConfigDeck] = []
    for view_model_deck in view_model.decks:
        models: List[SearchFieldConfigModel] = []
        for view_model_model in view_model_deck.models:
            if view_model_model.selected_field is not None:
                models.append(SearchFieldConfigModel(view_model_model.id, view_model_model.selected_field))
        if models:
            decks.append(SearchFieldConfigDeck(view_model_deck.id, models))
    return SearchFieldConfig(decks)

def load_search_field_config() -> SearchFieldConfig:
    config = mw.addonManager.getConfig(__name__)
    if 'search_fields' in config:
        return from_dict(SearchFieldConfig, config['search_fields'])
    return SearchFieldConfig([])

def save_search_field_config(search_fields_config: SearchFieldConfig):
    if search_fields_config.decks:
        config = {
            'search_fields': dataclasses.asdict(search_fields_config)
        }
    else: 
        config = { }
    mw.addonManager.writeConfig(__name__, config)
    tooltip('Config Saved: {}'.format(config))

def selected_field_changed(model, view_model, selected_field):
    # Update the view model, convert it back into the model, and save the model.
    model.selected_field = None if selected_field == 'Disabled' else selected_field
    config = search_fields_config(view_model)
    save_search_field_config(config)

def show_settings():
    config = load_search_field_config()
    view_model = search_fields_config_view_model(config)

    dialog = QDialog()
    dialog.setWindowTitle("Chinese Stats (Settings):")
    dialog.setFixedWidth(500)
    dialog.setMinimumHeight(640)
    
    layout = QVBoxLayout()

    scrollable_widget = QWidget()
    scrollable_widget.setLayout(layout)
    scrollable_widget.setFixedWidth(450)

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setWidget(scrollable_widget)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll_area.setFixedWidth(480)

    main_layout = QVBoxLayout(dialog)
    main_layout.addWidget(scroll_area)
    
    field_search_setting_label = QLabel('Choose which field to search within each deck and note type.')
    layout.addWidget(field_search_setting_label)
    layout.addSpacing(8)

    for deck in view_model.decks:
        deck_layout = QVBoxLayout()
        deck_box = QGroupBox(deck.name)
        deck_box.setLayout(deck_layout)
        
        for model in deck.models:
            model_layout = QHBoxLayout()

            model_label = QLabel(model.name)
            model_layout.addWidget(model_label)

            field_selector = QComboBox()
            # Prevent the scroll wheel from changing the value.
            field_selector.wheelEvent = lambda event: None
            field_selector.addItem('Disabled')
            field_selector.addItems(model.fields)
            field_selector.setCurrentText(model.selected_field or 'Disabled')
            field_selector.currentTextChanged.connect(functools.partial(selected_field_changed, model, view_model))
            model_layout.addWidget(field_selector)

            deck_layout.addLayout(model_layout)

        layout.addWidget(deck_box)
        layout.addSpacing(8)

    layout.addStretch(1)

    dialog.exec_()


stats_action = QAction("Chinese Stats (Stats)", mw)
qconnect(stats_action.triggered, show_webview)
mw.form.menuTools.addAction(stats_action)

settings_action = QAction("Chinese Stats (Settings)", mw)
qconnect(settings_action.triggered, show_settings)
mw.form.menuTools.addAction(settings_action)

# Kick off loading the data since it takes a couple seconds.
load_data_thread = threading.Thread(target=load_data)
load_data_thread.start()