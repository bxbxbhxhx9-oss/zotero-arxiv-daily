from .protocol import Paper
import math
from html import escape


framework = """
<!DOCTYPE HTML>
<html>
<head>
  <style>
    .star-wrapper {
      font-size: 1.3em; /* 调整星星大小 */
      line-height: 1; /* 确保垂直对齐 */
      display: inline-flex;
      align-items: center; /* 保持对齐 */
    }
    .half-star {
      display: inline-block;
      width: 0.5em; /* 半颗星的宽度 */
      overflow: hidden;
      white-space: nowrap;
      vertical-align: middle;
    }
    .full-star {
      vertical-align: middle;
    }
  </style>
</head>
<body>

<div>
    __CONTENT__
</div>

<br><br>
<div>
To unsubscribe, remove your email in your Github Action setting.
</div>

</body>
</html>
"""

def get_empty_html():
  block_template = """
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
  <tr>
    <td style="font-size: 20px; font-weight: bold; color: #333;">
        今日未检索到符合条件的新论文
    </td>
  </tr>
  </table>
  """
  return block_template


def get_selection_html(
    shortlist: list[Paper], candidate_count: int | None, selected_count: int
) -> str:
    if not shortlist:
        return ""
    rows = []
    for index, paper in enumerate(shortlist, start=1):
        title = escape(paper.title)
        url = escape(paper.url or paper.pdf_url or "", quote=True)
        score = f"{paper.score:.3f}" if paper.score is not None else "未评分"
        selected = "深度分析" if index <= selected_count else "Top 10 候选"
        rows.append(
            "<tr>"
            f'<td style="padding: 4px 8px;">{index}</td>'
            f'<td style="padding: 4px 8px;"><a href="{url}">{title}</a></td>'
            f'<td style="padding: 4px 8px;">{score}</td>'
            f'<td style="padding: 4px 8px;">{selected}</td>'
            "</tr>"
        )
    total = candidate_count if candidate_count is not None else len(shortlist)
    return (
        '<div style="font-family: Arial, sans-serif; margin-bottom: 16px;">'
        f"<strong>筛选轨迹：</strong>检索 {total} 篇，按 Zotero 文献库相关性得到 Top 10，"
        f"最终选择 {selected_count} 篇进行全文证据分析。"
        '<table border="1" cellpadding="0" cellspacing="0" width="100%" '
        'style="border-collapse: collapse; margin-top: 8px; font-size: 13px;">'
        "<tr><th>排名</th><th>论文</th><th>相关性</th><th>状态</th></tr>"
        + "".join(rows)
        + "</table></div>"
    )

def get_block_html(title:str, authors:str, rate:str, tldr:str, pdf_url:str, affiliations:str=None):
    analysis_html = escape(tldr or "分析未生成").replace("\n", "<br>")
    safe_title = escape(title)
    safe_authors = escape(authors)
    safe_affiliations = escape(affiliations or "机构信息未提供")
    safe_pdf_url = escape(pdf_url or "", quote=True)
    block_template = """
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
    <tr>
        <td style="font-size: 20px; font-weight: bold; color: #333;">
            {title}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #666; padding: 8px 0;">
            {authors}
            <br>
            <i>{affiliations}</i>
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>相关性评分：</strong> {rate}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>逐篇严谨分析：</strong><br>{analysis_html}
        </td>
    </tr>

    <tr>
        <td style="padding: 8px 0;">
            <a href="{pdf_url}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #d9534f; padding: 8px 16px; border-radius: 4px;">论文原文</a>
        </td>
    </tr>
</table>
"""
    return block_template.format(
        title=safe_title,
        authors=safe_authors,
        rate=rate,
        analysis_html=analysis_html,
        pdf_url=safe_pdf_url,
        affiliations=safe_affiliations,
    )

def get_stars(score:float):
    full_star = '<span class="full-star">⭐</span>'
    half_star = '<span class="half-star">⭐</span>'
    low = 6
    high = 8
    if score <= low:
        return ''
    elif score >= high:
        return full_star * 5
    else:
        interval = (high-low) / 10
        star_num = math.ceil((score-low) / interval)
        full_star_num = int(star_num/2)
        half_star_num = star_num - full_star_num * 2
        return '<div class="star-wrapper">'+full_star * full_star_num + half_star * half_star_num + '</div>'


def render_email(
    papers: list[Paper],
    shortlist: list[Paper] | None = None,
    candidate_count: int | None = None,
) -> str:
    parts = []
    if len(papers) == 0 :
        return framework.replace('__CONTENT__', get_empty_html())
    
    for p in papers:
        #rate = get_stars(p.score)
        rate = round(p.score, 1) if p.score is not None else 'Unknown'
        author_list = [a for a in p.authors]
        num_authors = len(author_list)
        if num_authors <= 5:
            authors = ', '.join(author_list)
        else:
            authors = ', '.join(author_list[:3] + ['...'] + author_list[-2:])
        if p.affiliations is not None:
            affiliations = p.affiliations[:5]
            affiliations = ', '.join(affiliations)
            if len(p.affiliations) > 5:
                affiliations += ', ...'
        else:
            affiliations = 'Unknown Affiliation'
        parts.append(get_block_html(p.title, authors, rate, p.tldr, p.pdf_url, affiliations))

    selection = get_selection_html(shortlist or [], candidate_count, len(papers))
    content = selection + '<br>' + '</br><br>'.join(parts) + '</br>'
    return framework.replace('__CONTENT__', content)
