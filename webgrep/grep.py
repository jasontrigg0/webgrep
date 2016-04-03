"""
Code to run grep commands.
grep("lucky","http://www.google.com")
Returns a list of paths from the root node to DOM elements containing the word "lucky"
"""
from utils import follow_path, select, get_soup, node_to_str
import re
import itertools
import bs4

def grep(grep, target, css = None, phantomjs = False):
    if isinstance(target,str):
        soup = get_soup(target, phantomjs, html_file = None, no_cache = True)
    elif isinstance(target,bs4.BeautifulSoup) or isinstance(target,bs4.element.Tag):
        soup = target
    else:
        raise Exception("ERROR: lookup input should be a url string or BeautifulSoup object")
    if css:
        soup = select(css, soup)
    csv_rows = main_grep(grep, soup, relative=False, verbose = False)
    output = _rows2csv(csv_rows[:10])
    print output
    if len(csv_rows) > 10:
        print "[truncated to 10 results...]"
        
def _rows2csv(rows):
    """http://stackoverflow.com/a/9157370"""
    import io
    import csv
    output = io.BytesIO()
    wr = csv.writer(output)
    for r in rows:
        wr.writerow([s.encode("utf-8") for s in r])
    return output.getvalue().strip()
    
def main_grep(grep, soup, relative, verbose):
    if relative:
        relative_node = _find_nodes(relative, soup)[0]
    else:
        relative_node = None
    csv_header = ["match","location"] + ["nearby"+str(i) for i in range(9)]
    csv_rows = [csv_header] + list(_web_grep_iter(grep, soup, relative_node))
    if not verbose:
        csv_rows = [r[:2] for r in csv_rows] #drop neighbor columns
    return csv_rows


def _web_grep_iter(item, soup, relative_node=None):
    nodes = _find_nodes(item, soup)
    max_levels = 3
    max_sibs_per_level = 3
    root_path = _path_to(soup)
    for n in nodes:
        path = _relative_path(root_path,_path_to(n))
        nearby = list(_get_all_nearby(soup, path, max_levels, max_sibs_per_level))
        nearby = nearby + [""] * (max_levels * max_sibs_per_level - len(nearby))
        if relative_node:
            output_path = _relative_path(_path_to(relative_node), _path_to(n))
        else:
            output_path = path
        r_out = [node_to_str(n)] + [" " + ",".join([str(i) for i in output_path])] + [node_to_str(i) for i in nearby]
        yield r_out

        
def _relative_path(path1, path2):
    """
    path on the tree to get from node1 to node2
    """
    #  from 1,2,3   to 1,2,3,7,0,2 =    7,0,2
    #  from 1,2,3,4 to 1,2,3,7,0,2 = -1,7,0,2
    if path2[:len(path1)] == path1:
        return path2[len(path1):]
    else:
        return [-1] + _relative_path(path1[:-1],path2)

    
def _path_to(node):
    ancestor_list = list(node.parents)[::-1] + [node] #starting from top of the tree
    return [n.parent.contents.index(n) for n in ancestor_list[1:]]


def _get_all_nearby(soup, path, max_levels, max_sibs_per_level):
    all_sib_lists = _get_siblings_by_depth(soup, path, max_sibs_per_level)
    all_sib_lists = list(itertools.islice(all_sib_lists, max_levels))
    for sib_list in all_sib_lists:
        for sib in sib_list:
            yield sib

            
def _get_siblings_by_depth(soup, path, max_sibs_per_depth = 3):
    for depth in range(len(path))[::-1]:
        sib_list = _get_nearest_siblings(soup, path, depth)
        sib_list = list(itertools.islice(sib_list, max_sibs_per_depth))
        if sib_list:
            yield sib_list

            
def _get_nearest_siblings(soup, path, depth):
    """Return siblings of the path location starting with the nearest
    eg 
    [1,3,2] -> [[1,3,1], [1,3,3], [1,3,0], [1,3,4], [1,3,5], [1,3,6]]
    """
    parent_node = follow_path(soup, path[:depth])[0]
    siblings_cnt = len(parent_node.contents)
    sibling_index = path[depth]
    for diff1 in range(1,siblings_cnt):
        for mult in [1,-1]:
            new_sibling_index = sibling_index + (mult * diff1)
            if new_sibling_index <  0 or \
               new_sibling_index >= siblings_cnt: 
                continue
            output = follow_path(soup, path[:depth] + [new_sibling_index] + path[depth+1:])
            if output:
                yield output[0]


def _find_nodes(item, soup):
    regex = re.escape(item)
    nodes1 = soup.find_all(text=re.compile(regex))
    nodes2 = soup.find_all(html=re.compile(regex))
    nodes = nodes1 + nodes2
    nodes = [_find_proper_node(n) for n in nodes]
    return nodes

def _find_proper_node(node):
    """Takes a node returned from soup.find_all and finds the parent or grandparent node we actually wanted.
    For example soup.find_all returns a separate node of the text of a link instead of the link node itself.
    """
    #jtrigg@20160307:
    #including <td> makes it harder to grep tables -- removing
    #until I find a good reason to put it back
    change_nodes = ["a"] #, "td"]
    if (node.parent.name in change_nodes and len(node.parent.contents) == 1):
        return _find_proper_node(node.parent)
    elif not isinstance(node, bs4.element.Tag) and isinstance(node.parent, bs4.element.Tag):
        return node.parent
    else:
        return node

