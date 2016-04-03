"""
Code to run lookup. 
lookup(["1","2","3"],"http://www.google.com")
Returns a 2-d array of the elements at path "1,2,3" from the root node in "http://www.google.com"
"""
from utils import follow_path, select, get_soup, node_to_str
import re
import bs4

def lookup(path, target, css = None, phantomjs = False, print_url = False, return_soup = False):
    if isinstance(target,str):
        soup = get_soup(target, phantomjs, html_file = None, no_cache = True)
    elif isinstance(target,bs4.BeautifulSoup) or isinstance(target,bs4.element.Tag):
        soup = target
    else:
        raise Exception("ERROR: lookup input should be a url string or BeautifulSoup object")
    path = path.strip().split(",")
    if css:
        soup = select(css, soup)[0]
    csv_rows = main_follow_path([path], soup, relative = False, print_url=print_url, return_soup=return_soup)
    wildcard_cnt = len([e for e in path if e == "-"])
    if wildcard_cnt == 0:
        return csv_rows[0][0]
    elif wildcard_cnt == 1:
        return [r[0] for r in csv_rows]
    else:
        return csv_rows
    
def main_follow_path(all_paths, soup, relative, print_url, return_soup = False):
    csv_rows = []
    for path in all_paths:
        if path.count("-") > 2:
            raise Exception("ERROR: more than two wildcards ('-') in step list")
        if relative:
            path_relative = list(_web_grep_iter(relative, soup))[0][1].split(',')
            path = path_relative + path
        csv_rows += _write_path_iter(path, soup, print_url, return_soup)
    return csv_rows

def _write_path_iter(path, soup, print_url, return_soup):
    def process_node(n, print_url, return_soup):
        if return_soup:
            return n
        else:
            return node_to_str(n, print_url, max_length=None)
        
    l = follow_path(soup,path)
    for elt in l:
        if not isinstance(elt,list):
            elt = [elt]
        r = [process_node(n, print_url, return_soup) for n in elt]
        yield r

