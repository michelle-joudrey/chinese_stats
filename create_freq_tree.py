import os
import sys
import pickle

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
from ahocorapy.keywordtree import KeywordTree
    
addon_directory = os.path.dirname(__file__)

# Search the sentences for words in the frequency list
freq_file_path = os.path.join(addon_directory, 'freq.txt')
freq_file = open(freq_file_path, encoding='utf_8_sig')
freq_data = freq_file.read().splitlines()

kwtree = KeywordTree(case_insensitive=True)
for word in freq_data:
    kwtree.add(word)
kwtree.finalize()  

kwtree_file = open("freq_tree.pickle", "wb")
pickle.dump(kwtree, kwtree_file)
kwtree_file.close()