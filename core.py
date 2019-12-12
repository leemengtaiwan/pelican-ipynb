"""
Core module that handles the conversion from notebook to HTML plus some utilities
"""
from __future__ import absolute_import, print_function, division

import os
import re
from copy import deepcopy

import jinja2
from pygments.formatters import HtmlFormatter

import IPython
try:
    # Jupyter
    from traitlets.config import Config
    from traitlets import Integer
except ImportError:
    # IPython < 4.0
    from IPython.config import Config
    from IPython.utils.traitlets import Integer

try:
    # Jupyter
    from nbconvert.preprocessors import Preprocessor
except ImportError:
    # IPython < 4.0
    from IPython.nbconvert.preprocessors import Preprocessor

try:
    # Jupyter
    import nbconvert
except ImportError:
    # IPython < 4.0
    import IPython.nbconvert as nbconvert

from nbconvert.exporters import HTMLExporter
try:
    from nbconvert.filters.highlight import _pygment_highlight
except ImportError:
    # IPython < 2.0
    from nbconvert.filters.highlight import _pygments_highlight

try:
    from nbconvert.nbconvertapp import NbConvertApp
except ImportError:
    from IPython.nbconvert.nbconvertapp import NbConvertApp

try:
    from bs4 import BeautifulSoup
except:
    BeautifulSoup = None

from pygments.formatters import HtmlFormatter

from copy import deepcopy


LATEX_CUSTOM_SCRIPT = """
<script type="text/javascript">if (!document.getElementById('mathjaxscript_pelican_#%@#$@#')) {
    var mathjaxscript = document.createElement('script');
    mathjaxscript.id = 'mathjaxscript_pelican_#%@#$@#';
    mathjaxscript.type = 'text/javascript';
    mathjaxscript.src = '//cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.1/MathJax.js?config=TeX-AMS-MML_HTMLorMML';
    mathjaxscript[(window.opera ? "innerHTML" : "text")] =
        "MathJax.Hub.Config({" +
        "    config: ['MMLorHTML.js']," +
        "    TeX: { extensions: ['AMSmath.js','AMSsymbols.js','noErrors.js','noUndefined.js'], equationNumbers: { autoNumber: 'AMS' } }," +
        "    jax: ['input/TeX','input/MathML','output/HTML-CSS']," +
        "    extensions: ['tex2jax.js','mml2jax.js','MathMenu.js','MathZoom.js']," +
        "    displayAlign: 'center'," +
        "    displayIndent: '0em'," +
        "    showMathMenu: true," +
        "    tex2jax: { " +
        "        inlineMath: [ ['$','$'] ], " +
        "        displayMath: [ ['$$','$$'] ]," +
        "        processEscapes: true," +
        "        preview: 'TeX'," +
        "    }, " +
        "    'HTML-CSS': { " +
        " linebreaks: { automatic: true, width: '95% container' }, " +
        "        styles: { '.MathJax_Display, .MathJax .mo, .MathJax .mi, .MathJax .mn': {color: 'black ! important'} }" +
        "    } " +
        "}); ";
    (document.body || document.getElementsByTagName('head')[0]).appendChild(mathjaxscript);
}
</script>
"""


def get_config():
    """Load and return the user's nbconvert configuration
    """
    app = NbConvertApp()
    app.load_config_file()
    return app.config


def get_html_from_filepath(filepath, start=0, end=None, preprocessors=[], template=None):
    """Return the HTML from a Jupyter Notebook
    """
    template_file = 'basic'
    extra_loaders = []
    if template:
        extra_loaders.append(jinja2.FileSystemLoader([os.path.dirname(template)]))
        template_file = os.path.basename(template)

    config = get_config()
    config.update({'CSSHTMLHeaderTransformer': {
                        'enabled': True,
                        'highlight_class': '.highlight-ipynb'},
                     'SubCell': {
                        'enabled':True,
                        'start':start,
                        'end':end}})
    exporter = HTMLExporter(config=config,
                            template_file=template_file,
                            extra_loaders=extra_loaders,
                            filters={'highlight2html': custom_highlighter},
                            preprocessors=[SubCell] + preprocessors)

    config.CSSHTMLHeaderPreprocessor.highlight_class = " .highlight pre "
    content, info = exporter.from_filename(filepath)

    if BeautifulSoup:
        soup = BeautifulSoup(content, 'html.parser')
        for i in soup.findAll('div', {'class': 'input'}):
            if i.findChildren()[1].find(text='#ignore') is not None:
                i.extract()

            # transform code block to block-quote for pretty rendering
            elif i.findChildren()[1].find(text='#blockquote') is not None:
                pre = i.find('pre')
                parent_div = pre.parent # div to replace code with blockquote

                # get raw text after block-quote keyword
                raw_text = ''
                for e in pre.contents[2:]:
                    try:
                        raw_text += e.text
                    except AttributeError:
                        if e.replace('　', ' ').replace(' ', ' ') == ' ':
                            raw_text += e
                # delete <pre> tag from parent div
                pre.extract()

                # insert <blockquote> tag into parent div
                p = soup.new_tag('p')
                p.append(raw_text)
                block_quote = soup.new_tag('blockquote')
                block_quote.append(p)
                parent_div.append(block_quote)

        # remove input and output prompt
        for prompt in soup.findAll('div', {'class': 'prompt'}):
            prompt.extract()

        # add classes for tables to apply bootstrap style
        # for t in soup.findAll('table', {'class': 'dataframe'}):
        for t in soup.findAll('table'):
            t['class'] = t.get('class', []) + ['table', 'table-striped', 'table-responsive']

        # generate html for templated markdown cells
        mp4_options = 'loop autoplay muted playsinline'  # mp4 video default options
        for i in soup.findAll('div', {'class': 'text_cell_render'}):
            class_str = ""
            style_str = ""

            texts = i.findChildren()
            template_settings = {
                '!article': ['article_title', 'article_link', 'image_filename'],
                '!quote': ['quote_text', 'author_into'],
                '!mp4': ['mp4_file', 'image_file', 'description'],
                '!image': ['image_file', 'description', 'source_link', 'source_name'],
                '!youtube': ['video_id', 'description', 'start', 'end'],
            }
            # get settings for template keywords
            values = []
            if texts and texts[0].text in template_settings:
                keyword = texts[0].text
                for e in i.findAll('li'):
                    text = e.text
                    if text == 'dark':
                        # 參照 pelican-jupyter-notebook/themes/Hola10/static/css/darkmode.css
                        style_str += "mix-blend-mode: initial;"
                    elif text.startswith("style:"):
                        text = text.replace("style:", "")
                        style_str += text

                    # special keyword for mp4 video options
                    elif keyword == '!mp4' and 'options:' in text:
                        if 'no-loop' in text.replace('_', '-'):
                            mp4_options = mp4_options.replace("loop ", "")
                        if 'no-autoplay' in text.replace('_', '-'):
                            mp4_options = mp4_options.replace("autoplay ", "")
                        if 'controls' in text:
                            mp4_options += " controls"
                    else:
                        values.append(text)

                style_str = f'style="{style_str}"' if style_str else ''
                class_str = f'class="{class_str}"' if class_str else ''

            if not values:
                continue
            html_str = ''
            # article covers for digest
            if keyword == '!article':
                title, link, image_filename = values
                anchor_link = title.replace(' ', ' ').replace('　', ' ').replace(' ', '-')
                html_str = """
                <h2 id="{anchor_link}">
                    <a href="{link}" target="_blank">{title}</a><a class="anchor-link" href="#{anchor_link}">¶</a>
                </h2>
                <center>
                    <a href="{link}" target="_blank">
                        <img src="{{filename}}images/digests/{image_filename}" {style_str}>
                    </a>
                    <br>
                </center>
                """.format(filename='static', anchor_link=anchor_link,
                           link=link, title=title, image_filename=image_filename, style_str=style_str)
            elif keyword == '!quote':
                author_intro = ''
                if len(values) > 1:
                    author_intro = """
                    <span style="float:right;margin-right: 1.5rem">─ {author_intro}</span>
                    """.format(author_intro=values[1])
                html_str = """
                <blockquote>
                    <p>
                        {quote}
                        <br>
                        {author_intro}
                        <br>
                    </p>
                </blockquote>
                """.format(quote=values[0], author_intro=author_intro)
            elif keyword == '!mp4':
                mp4_file, description, image_file, source_str, source_link = [''] * 5
                if len(values) == 1:
                    mp4_file = values[0]
                elif len(values) == 2:
                    for v in values:
                        v = v.lower()
                        if '.mp4' in v:
                            mp4_file = v
                        elif '.jpg' in v or '.png' in v or '.svg' in v or '.jpeg' in v:
                            image_file = v
                        else:
                            description = v
                elif len(values) == 3:
                    mp4_file, image_file, description = values
                    assert '.mp4' in mp4_file, '沒有對應的 mp4 檔案！'
                elif len(values) == 4:
                    mp4_file, image_file, description, source_link = values
                    assert '.mp4' in mp4_file, '沒有對應的 mp4 檔案！'
                    assert 'http' in source_link, '沒有對應的網址！'

                if description:
                    if source_link:
                        source_str = """
                        （<a href="{source_link}" target="_blank">圖片來源</a>）
                        """.format(source_link=source_link)

                    description = """
                    <center>
                        {description}{source_str}
                        <br/>
                        <br/>
                    </center>
                    """.format(description=description, source_str=source_str)
                else:
                    description = '<br>'

                html_str = """
                <video {mp4_options} poster="{{filename}}{image_file}" {class_str} {style_str}> 
                  <source src="{{filename}}{mp4_file}" type="video/mp4">
                    您的瀏覽器不支援影片標籤，請留言通知我：S
                </video>
                {description}
                """.format(mp4_options=mp4_options, filename='static', mp4_file=mp4_file, image_file=image_file,
                           class_str=class_str, style_str=style_str, description=description)
            elif keyword == '!image':
                if len(values) == 1:
                    html_str = """
                    <img {class_str} {style_str} src="{{filename}}images/{image_file}"/>
                    <br>
                    """.format(class_str=class_str, style_str=style_str, filename='static', image_file=values[0])
                else:
                    description = values[1]
                    source_str = ''
                    if len(values) == 3:
                        source_link = values[2]
                        source_str = """
                        （<a href="{source_link}" target="_blank">圖片來源</a>）
                        """.format(source_link=source_link)
                    elif len(values) == 4:
                        source_link, source_name = values[2:]
                        source_str = """
                        （圖片來源：<a href="{source_link}" target="_blank">{source_name}</a>）
                        """.format(source_link=source_link, source_name=source_name)

                    html_str = """
                    <center>
                        <img {class_str} {style_str} src="{{filename}}/images/{image_file}">
                    </center>
                    <center>
                        {description}{source_str}
                        <br>
                        <br>
                    </center>
                    """.format(class_str=class_str, style_str=style_str, filename='static', image_file=values[0],
                               description=description, source_str=source_str)
            elif keyword == '!youtube':
                period_str, description = '', ''
                if len(values) == 1:
                    video_id = values[0]
                elif len(values) == 2:
                    video_id, description = values
                elif len(values) == 3:
                    video_id, description, start = values
                    period_str = f'?start={start}'
                elif len(values) == 4:
                    video_id, description, start, end = values
                    period_str = f'?start={start}&end={end}'

                if description:
                    description = """
                    <center>
                        {description}
                        <br/>
                        <br/>
                    </center>
                    """.format(description=description,)
                else:
                    description = '<br>'

                html_str = """
                <div class="resp-container">
                    <iframe class="resp-iframe" 
                            src="https://www.youtube-nocookie.com/embed/{video_id}{period_str}" 
                            frameborder="0" 
                            allow="accelerometer; 
                            autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen>
                    </iframe>
                </div>
                {description}
                """.format(video_id=video_id, period_str=period_str, description=description)

            # delete existing template setting
            p = i.find('p')
            ul = i.find('ul')
            p.extract()
            ul.extract()

            # insert generated html string
            i.append(BeautifulSoup(html_str, 'html.parser'))

        content = soup.decode(formatter="minimal")

    return content, info


def parse_css(content, info, fix_css=True, ignore_css=False):
    """
    General fixes for the notebook generated html

    fix_css is to do a basic filter to remove extra CSS from the Jupyter CSS
    ignore_css is to not include at all the Jupyter CSS
    """
    def style_tag(styles):
        return '<style type=\"text/css\">{0}</style>'.format(styles)

    def filter_css(style):
        """
        This is a little bit of a Hack.
        Jupyter returns a lot of CSS including its own bootstrap.
        We try to get only the Jupyter Notebook CSS without the extra stuff.
        """
        index = style.find('/*!\n*\n* IPython notebook\n*\n*/')
        if index > 0:
            style = style[index:]
        index = style.find('/*!\n*\n* IPython notebook webapp\n*\n*/')
        if index > 0:
            style = style[:index]

        style = re.sub(r'color\:\#0+(;)?', '', style)
        style = re.sub(r'\.rendered_html[a-z0-9,._ ]*\{[a-z0-9:;%.#\-\s\n]+\}', '', style)
        return style_tag(style)

    if ignore_css:
        content = content + LATEX_CUSTOM_SCRIPT
        # content = content
    else:
        if fix_css:
            jupyter_css = '\n'.join(filter_css(style) for style in info['inlining']['css'])
        else:
            jupyter_css = '\n'.join(style_tag(style) for style in info['inlining']['css'])
        content = jupyter_css + content + LATEX_CUSTOM_SCRIPT
    return content


def custom_highlighter(source, language='python', metadata=None):
    """
    Makes the syntax highlighting from pygments have prefix(`highlight-ipynb`)
    So it doesn't break the theme pygments

    This modifies both css prefixes and html tags

    Returns new html content
    """
    if not language:
        language = 'python'

    formatter = HtmlFormatter(cssclass='highlight-ipynb')
    output = _pygments_highlight(source, formatter, language, metadata)
    output = output.replace('<pre>', '<pre class="ipynb">')
    return output

#----------------------------------------------------------------------
# Create a preprocessor to slice notebook by cells

class SliceIndex(Integer):
    """An integer trait that accepts None"""
    default_value = None

    def validate(self, obj, value):
        if value is None:
            return value
        else:
            return super(SliceIndex, self).validate(obj, value)


class SubCell(Preprocessor):
    """A preprocessor to select a slice of the cells of a notebook"""
    start = SliceIndex(0, config=True, help="first cell of notebook")
    end = SliceIndex(None, config=True, help="last cell of notebook")

    def preprocess(self, nb, resources):
        nbc = deepcopy(nb)
        nbc.cells = nbc.cells[self.start:self.end]
        return nbc, resources
