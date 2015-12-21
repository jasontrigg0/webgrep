#!/usr/bin/env python
import argparse
from bs4 import BeautifulSoup
import urllib2
import re
import csv
import sys
import os.path
import tempfile

def readCL():
    parser = argparse.ArgumentParser()
    parser.add_argument("-g","--grep",help="item to grep from the website")
    parser.add_argument("-l","--location",nargs="*",help="location within the page to look. given as a csv list of steps. '-' is a wildcard. eg: 1,1,0,13,9,1,5,3,1,-,0")
    parser.add_argument("-u","--url",help="url to look in")
    parser.add_argument("-f","--html_file")
    parser.add_argument("-r","--relative",help="grep the -g arg position relative to -r arg instead of absolute position on the page. Useful if the desired section of the page remains the same but other layout varies.")
    parser.add_argument("--print_url",action="store_true",help="print link urls instead of link text")
    # parser.add_argument("--no_cache",help="By default webgrep caches the last webpage you downloaded for faster rerunning. Use no_cache to override.")
    parser.add_argument("--phantomjs",action="store_true",help="use phantomjs to parse the website for DOM elements that are loaded using javascript")
    parser.add_argument("-v","--verbose",action="store_true")
    args = parser.parse_args()
    if args.location:
        step_list = [l.strip().split(",") for l in args.location]
    args.no_cache = True
    return args.grep, args.url, args.html_file, step_list, args.relative, args.print_url, args.no_cache, args.phantomjs, args.verbose

def steps_to(node):
    ancestor_list = list(node.parents)[::-1] + [node] #starting from top of the tree
    return [n.parent.contents.index(n) for n in ancestor_list[1:]]

def relative_steps(steps1, steps2):
    """
    steps on the tree to get from node1 to node2
    """
    #  from 1,2,3 to 1,2,3,7,0,2 = 7,0,2
    if steps2[:len(steps1)] == steps1:
        return steps2[len(steps1):]
    else:
        return [-1] + relative_steps(steps1[:-1],steps2)

def follow_steps(node,step_list,nested=True):
    return list(_follow_steps(node,step_list,nested))

def _follow_steps(node, step_list, nested=True):
    if not step_list:
        yield node
    elif step_list[0] == "-":
        if not hasattr(node,"contents"): return
        for n1 in node.contents:
            #don't encase the last '-' in list because those are single items
            if nested and "-" in step_list[1:]: 
                yield [n2 for n2 in follow_steps(n1,step_list[1:],nested)]
            else:
                for n2 in follow_steps(n1,step_list[1:],nested):
                    yield n2
    elif step_list[0] == "-1":
        for n in follow_steps(node.parent, step_list[1:],nested):
            yield n
    else:
        step = int(step_list[0])
        if not hasattr(node,"contents"): return
        if len(node.contents) <= step: return
        n1 = node.contents[step]
        for n2 in follow_steps(n1, step_list[1:],nested=True):
            yield n2


def trim_with_ellipses(string, max_len):
    string = string.replace("\n","").replace("\r","")
    if len(string) > max_len:
        return string[:(max_len-3)] + "..."
    else:
        return string



def web_grep(item, url):
    soup = get_soup(url)
    return list(_web_grep(item, soup))

def _find_nodes(item, soup):
    nodes1 = soup.find_all(text=re.compile(item))
    nodes2 = soup.find_all(html=re.compile(item))
    nodes = nodes1 + nodes2
    return nodes

def _web_grep(item, soup, relative_node=None):
    nodes = _find_nodes(item, soup)
    max_nearby_locs = 3
    max_nearby_sibs = 3
    for n in nodes:
        nearby_items = []
        step_list = steps_to(n)
        last_index   = step_list[-1]
        last_index_2 = step_list[-2]
        nearby_found_locs = set()
        for from_back in range(len(step_list)):
            if len(nearby_found_locs) >= max_nearby_locs: break
            step_list_mod = step_list[:]
            parent_node = follow_steps(soup, step_list[: -1 * from_back])
            assert len(parent_node) == 1
            siblings_cnt = len(parent_node[0].contents)
            sibling_index = step_list[-1 * from_back]
            sibling_found_cnt = 0
            for diff1 in range(1,siblings_cnt):
                for mult in [1,-1]:
                    if sibling_found_cnt >= max_nearby_sibs: break
                    new_sibling_index = sibling_index + (mult * diff1)
                    if new_sibling_index <  0 or \
                       new_sibling_index >= siblings_cnt: 
                        continue
                    step_list_mod[-1 *from_back] = new_sibling_index
                    try:
                        output = follow_steps(soup, step_list_mod)
                        if output:
                            sibling_found_cnt += 1
                            nearby_found_locs.add(from_back)
                            nearby_items.append(output[0])
                    except:
                        pass
        nearby_items = nearby_items + [""] * (max_nearby_locs * max_nearby_sibs - len(nearby_items))
        nearby_items = [trim_with_ellipses(unicode(i),50) for i in nearby_items]
        if relative_node:
            output_step_list = relative_steps(steps_to(relative_node), steps_to(n))
        else:
            output_step_list = step_list

        r_out = [trim_with_ellipses(unicode(n),50)] + [" " + ",".join([str(i) for i in output_step_list])] + nearby_items
        r_out = [i.encode("utf-8") for i in r_out]
        yield r_out


def get_href(elt):
    if "href" in getattr(elt,"attrs",[]):
        return elt["href"]
    elif "href" in getattr(elt.parent,"attrs",[]):
        return elt.parent["href"]



def write_steps(step_list, url, print_url):
    get_soup(url)
    return list(_write_steps(step_list, soup, print_url))

def _write_steps(step_list, soup, print_url):
    l = list(follow_steps(soup,step_list))
    for elt in l:
        if not isinstance(elt,list):
            elt = [elt]
        if print_url:
            r = [get_href(f).encode("utf-8") for f in elt if get_href(f)]
        else:
            r = [f.encode("utf-8") for f in elt]
        yield r

def get_cached_soup(no_cache, print_url, get_soup_fn):
    cache_file = "/tmp/.webgrep"
    if not no_cache:
        import cPickle
        if os.path.exists(cache_file):
            old_url, old_soup = cPickle.load(open(cache_file,'rb'))
            if old_url == print_url:
                soup = old_soup
            else:
                soup = get_soup_fn(url)
                save_soup(url, soup, cache_file)
        else:
            soup = get_soup_fn(url)
            save_soup(url, soup, cache_file)
    else:
        soup = get_soup_fn(url)
    return soup


def save_soup(url, soup, save_file):
    to_save = [url,soup]
    import cPickle
    try:
        cPickle.dump(to_save,open(save_file,'wb'))
    except RuntimeError:
        sys.stderr.write("WARNING: couldn't save website" + "\n")
        os.remove(save_file)
        

def get_soup(url):
    opener = urllib2.build_opener()
    opener.addheaders = [('User-agent', 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:40.0) Gecko/20100101 Firefox/40.0')]
    html = opener.open(url).read()
    soup = BeautifulSoup(html, "lxml")
    return soup

def run(cmd):
    import subprocess
    pipes = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    stdout, stderr = pipes.communicate()
    return_code = pipes.returncode
    return stdout, stderr, return_code


def get_phantomjs_soup(url):
    print_url_js_code = """var page = require('webpage').create();
page.open('"""+url+"""', function () {
    console.log(page.content);
    phantom.exit();
});
"""
    print_url_js_file = "/tmp/print_html.js"
    fd, f_path = tempfile.mkstemp()
    try:
        with os.fdopen(fd, "w") as f_in:
            f_in.write(print_url_js_code)
        html, _, _ = run("phantomjs " + f_path)
        soup = BeautifulSoup(html, "lxml")
        return soup
    finally:
        os.remove(f_path)

    
if __name__ == "__main__":
    grep, url, html_file, all_step_lists, relative, print_url, no_cache, phantomjs, verbose = readCL()
    if url and phantomjs:
        soup = get_phantomjs_soup(url)
    elif url:
        soup = get_cached_soup(no_cache, url, get_soup)
    elif html_file:
        soup = BeautifulSoup(open(html_file).read(), "lxml")
    else:
        raise Exception("Couldn't find input url or html_file!")

    if grep:
        if relative:
            relative_node = _find_nodes(relative, soup)[0]
        else:
            relative_node = None
        csv_header = ["match","location"] + ["nearby"+str(i) for i in range(9)]
        csv_rows = [csv_header] + list(_web_grep(grep, soup, relative_node))
        if not verbose:
            csv_rows = [r[:2] for r in csv_rows] #drop neighbor columns
        csv.writer(sys.stdout, lineterminator= '\n').writerows(csv_rows)
    elif all_step_lists:
        csv_rows = []
        for step_list in all_step_lists:
            if step_list.count("-") > 2:
                raise Exception("ERROR: more than two wildcards ('-') in step list")

            if relative:
                steps_to_relative = list(_web_grep(relative, soup))[0][1].split(',')
                step_list = steps_to_relative + step_list
            csv_rows += _write_steps(step_list, soup, print_url)
        csv.writer(sys.stdout, lineterminator= '\n').writerows(csv_rows)

