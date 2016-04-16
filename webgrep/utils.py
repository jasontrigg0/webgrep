#functions needed by both grep.py and lookup.py
import requests
from requests.adapters import HTTPAdapter
import bs4
import re
import distutils.spawn
import tempfile
import os.path
import os

STATE = []

def current_state():
    return STATE

def follow_path(node,path):
    return list(_follow_path_iter(node,path))

def _follow_path_iter(node, path):
    if not path or not path[0]:
        if isinstance(node, bs4.element.Tag):
            yield node
        elif node_to_str(node): #keep nodes with non-empty text
            yield node
        else:
            return
    elif path[0] == "-":
        if not hasattr(node,"contents"):
            return
        for n1 in node.contents:
            #don't encase the last '-' in path because those are single items
            if "-" in path[1:]:
                l = [n2 for n2 in follow_path(n1,path[1:])]
                #don't yield l if we didn't find anything
                if l:
                    yield l
                else:
                    continue
            else:
                for n2 in follow_path(n1,path[1:]):
                    yield n2
    elif path[0] == "-1":
        for n in follow_path(node.parent, path[1:]):
            yield n
    else:
        step = int(path[0])
        if not hasattr(node,"contents"): return
        if len(node.contents) <= step: return
        n1 = node.contents[step]
        for n2 in follow_path(n1, path[1:]):
            yield n2


def _split_css_selector(select):
    """.class1 > .class2 .class3" -> [("",".class1"), (">",".class2"), ("",".class3")]
    """
    # Regex example: "a > b c" -> ['a', ' ', '', '>', '', ' ', 'b', ' ', 'c']
    s = re.split("([> ])", select)
    output = []
    prev = ""
    for i in s:
        if i.strip() == ">":
            prev = ">"
        elif i.strip() != "": #eg a.some-class
            output.append((prev, i.strip()))
            prev = ""
    return output


def _select_one_level(relation, sub_sel, target_nodes):
    output_nodes = []
    for soup in target_nodes:
        args = {}
        if relation == ">":
            args["recursive"] = False
        if "." in sub_sel:
            css_tag, css_class = sub_sel.split(".")
            args["attrs"] = {"class":css_class}
            if css_tag:
                result_nodes = soup.find_all(css_tag, **args)
            else:
                result_nodes = soup.find_all(**args)
        elif "#" in sub_sel:
            css_tag, css_id = sub_sel.split("#")
            args["attrs"] = {"id":css_id}
            if css_tag:
                result_nodes = soup.find_all(css_tag, **args)
            else:
                result_nodes = soup.find_all(**args)
        else:
            css_tag = sub_sel
            result_nodes = soup.find_all(css_tag)
        output_nodes += result_nodes
    return output_nodes
        

def select(css_selector, target, phantomjs = False):
    """Input: jquery-style selector string
       eg: "head.big-class"
           "#wrapper3"
       Returns: List of nodes that match that pattern
    """
    global STATE
    STATE = _get_desc(target) + [css_selector]
    if isinstance(target,str):
        soup = get_soup(target, phantomjs=phantomjs)
    elif isinstance(target,bs4.BeautifulSoup) or isinstance(target,bs4.element.Tag):
        soup = target
    else:
        raise Exception("ERROR: lookup input should be a url string or BeautifulSoup object")
    
    #Split on ","
    output_nodes = []
    for s in css_selector.split(","):
        s = s.strip()
        target_nodes = [soup]
        for (relation, sub_sel) in _split_css_selector(s):
            target_nodes = _select_one_level(relation, sub_sel, target_nodes)
        output_nodes += target_nodes
        
    for i,n in enumerate(output_nodes):
        n.desc = (_get_desc(target) + [css_selector + " #" + str(i)])
    return output_nodes


def _get_desc(target):
    if isinstance(target, str):
        return  [target]
    elif getattr(target,"desc",[]) == None:
        return []
    else:
        return getattr(target,"desc",[])
    

#jtrigg@20160308 old version of select that returned a div that contained the list of matches
# def find_css(selector, soup):
#     output_parent = soup.new_tag("div")
#     search_nodes = css_selector(selector, soup)
#     for n in search_nodes:
#         output_parent.append(n)
#     return output_parent

def get_soup(url, phantomjs = False, html_file = False, no_cache = True):
    STATE = [url]
    if url and phantomjs:
        soup = _get_phantomjs_soup(url)
    elif url:
        soup = _get_cached_soup(no_cache, url, _url_to_soup)
    elif html_file:
        soup = _html_to_soup(open(html_file).read())
    else:
        raise Exception("Couldn't find input url or html_file!")
    soup.desc = [url]
    return soup

def _get_phantomjs_soup(url):
    print_url_js_code = """
var page = require('webpage').create();
page.open('"""+url+"""', function () {
    console.log(page.content);
    phantom.exit();
});
"""

    
#     print_url_js_code="""var page = require("webpage").create(),
#     url = '"""+url+"""';

# function onPageReady() {
#     var htmlContent = page.evaluate(function () {
#         return document.documentElement.outerHTML;
#     });

#     console.log(htmlContent);

#     phantom.exit();
# }

#     print_url_js_code = """ 
# var page = require('webpage').create();
# page.open('"""+url+"""', function (status) {
#     function checkReadyState() {
#         setTimeout(function () {
#             var readyState = page.evaluate(function () {
#                 return document.readyState;
#             });

#             if ("complete" === readyState) {
#                 console.log(page.content);
#                 phantom.exit();
#             } else {
#                 checkReadyState();
#             }
#         });
#     }

#     checkReadyState();
# });
# """
    
    print_url_js_code="""
    var page = require('webpage').create();    
    page.open('"""+url+"""', function (status) {
    if (status !== 'success') {
        console.log('Unable to load the address!');
        phantom.exit();
    } else {
        window.setTimeout(function () {
            console.log(page.content);
            phantom.exit();
        }, 5000); // Change timeout as required to allow sufficient time 
    }
});"""

    
    #tell phantomjs to wait until the website is loaded to download the content
    #http://stackoverflow.com/questions/11340038/phantomjs-not-waiting-for-full-page-load
#     print_url_js_code="""page.open('"""+url+"""', function (status) {
#     if (status !== 'success') {
#         console.log('Unable to load the address!');
#         phantom.exit();
#     } else {
#         window.setTimeout(function () {
#             page.render(output);
#             console.log(page.content);
#             phantom.exit();
#         }, 5000); // Change timeout as required to allow sufficient time 
#     }
# });"""
    if not distutils.spawn.find_executable("phantomjs"):
        raise Exception("ERROR! Can't find phantomjs. See http://phantomjs.org/build.html")
    fd, f_path = tempfile.mkstemp()
    try:
        with os.fdopen(fd, "w") as f_in:
            f_in.write(print_url_js_code)
        html, _, _ = _run("phantomjs " + f_path)
        soup = _html_to_soup(html)
        return soup
    except:
        # os.remove(f_path)
        raise
    finally:
        pass
        # os.remove(f_path)

def _get_cached_soup(no_cache, url, get_soup_fn):
    cache_file = "/tmp/.webgrep"
    if not no_cache:
        import cPickle
        if os.path.exists(cache_file):
            old_url, old_soup = cPickle.load(open(cache_file,'rb'))
            if old_url == url:
                soup = old_soup
            else:
                soup = get_soup_fn(url)
                _save_soup(url, soup, cache_file)
        else:
            soup = get_soup_fn(url)
            _save_soup(url, soup, cache_file)
    else:
        soup = get_soup_fn(url)
    return soup


def _save_soup(url, soup, save_file):
    to_save = [url,soup]
    import cPickle
    try:
        cPickle.dump(to_save,open(save_file,'wb'))
    except RuntimeError:
        sys.stderr.write("WARNING: couldn't save website" + "\n")
        os.remove(save_file)

def _html_to_soup(html):
    if isinstance(html, str):
        html = html.decode("utf-8","ignore")
    try:
        soup = bs4.BeautifulSoup(html, "lxml")
    except:
        soup = bs4.BeautifulSoup(html, "html.parser")
    return soup

def _url_to_soup(url):
    html = _get_webpage(url)
    return _html_to_soup(html)
    
def _run(cmd):
    import subprocess
    pipes = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    stdout, stderr = pipes.communicate()
    return_code = pipes.returncode
    return stdout, stderr, return_code

def _get_webpage(url):
    if not url.startswith("http"):
        url = "http://" + url
    headers = {'User-agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:40.0) Gecko/20100101 Firefox/40.0'}
    s = requests.Session()
    RETRIES = 5
    for i in range(RETRIES):
        try:
            return s.get(url, headers=headers, timeout=(10,10)).text
        except (requests.exceptions.RequestException, requests.Timeout, requests.exceptions.ReadTimeout) as e:
            if i < (RETRIES - 1):
                continue
            else:
                raise e
    
def node_to_str(node, print_url=False, max_length=50):
    if getattr(node, "name", "") in ["td"] and len(node.contents) == 1:
        return node_to_str(node.contents[0], print_url=print_url, max_length=max_length)
    if "href" in getattr(node,"attrs",[]) and print_url:
        s = (node["href"])
    elif hasattr(node,"text"):
        s = (node.text)
    else:
        s = (node)
    s = s.replace("\n","")
    if max_length:
        return _trim_with_ellipses(s,max_length)
    else:
        return s
    
def _trim_with_ellipses(string, max_len):
    string = string.replace("\n","").replace("\r","")
    if len(string) > max_len:
        return string[:(max_len-3)] + "..."
    else:
        return string
