import dataclasses
import functools
from aqt import mw
from aqt.utils import tooltip
from aqt.qt import *
from typing import Optional
from typing import List
from dataclasses import dataclass

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
from dacite import from_dict

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
    config = mw.addonManager.getConfig(__name__) or {}
    if 'search_fields' in config:
        return from_dict(SearchFieldConfig, config['search_fields'])
    return SearchFieldConfig([])

def save_search_field_config(search_fields_config: SearchFieldConfig):
    if search_fields_config.decks:
        config = {
            'search_fields': dataclasses.asdict(search_fields_config)
        }
    else: 
        config = {}
    mw.addonManager.writeConfig(__name__, config)
    tooltip("Config saved.")

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

# Show our config dialog when our addon's config is accessed in the Addons window.
mw.addonManager.setConfigAction(__name__, show_settings)