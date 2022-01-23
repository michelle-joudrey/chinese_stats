import os
import sys
import pickle
import json

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
from ahocorapy.keywordtree import KeywordTree
    
addon_directory = os.path.dirname(__file__)

hsk_file_path = os.path.join(addon_directory, 'hsk.json')
hsk_file = open(hsk_file_path, encoding='utf_8_sig')
hsk_data = json.load(hsk_file)

kwtree = KeywordTree(case_insensitive=True)
for word, _ in hsk_data.items():
    kwtree.add(word)
kwtree.finalize()  

kwtree_file = open("hsk_tree.pickle", "wb")
pickle.dump(kwtree, kwtree_file)
kwtree_file.close()