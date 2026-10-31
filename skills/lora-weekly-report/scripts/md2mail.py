#!/usr/bin/env python3
"""Turn the report markdown into a ready-to-send mail body (text + html).

Adds the 【AI 代发】 prefix and the forward header block, and emits:
  mail.txt   plain-text fallback (tables flattened to bullet lines)
  mail.html  same content with real <table> and clickable PR links

Usage:
  python md2mail.py --md reports/2026-10-30-lora-weekly.md --out runs/2026-10-30
"""
import argparse
import datetime
import html
import io
import os
import re

DEFAULT_TO = "xumingzhe4@huawei.com"
DEFAULT_SENDER = "3248569436@qq.com"


def split_link(cell):
    m = re.match(r"\[(.+?)\]\((\S+?)\)$", cell)
    if m:
        return m.group(1), m.group(2)
    return cell, None


def strip_md(t):
    t = re.sub(r"\[(.+?)\]\((\S+?)\)", r"\1", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    return t.strip()


def plain(t):
    """Markdown -> plain text, keeping link targets visible for mail fallbacks."""
    t = re.sub(r"\[(.+?)\]\((\S+?)\)", r"\1（\2）", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    return t.strip()


def inline_html(t):
    out = []
    pos = 0
    for m in re.finditer(r"\[(.+?)\]\((\S+?)\)|\*\*(.+?)\*\*|`([^`]+)`", t):
        out.append(html.escape(t[pos:m.start()]))
        if m.group(1) is not None:
            out.append('<a href="%s" style="color:#0b4f8a;">%s</a>'
                       % (html.escape(m.group(2), quote=True), html.escape(m.group(1))))
        elif m.group(3) is not None:
            out.append("<strong>%s</strong>" % html.escape(m.group(3)))
        else:
            out.append('<code>%s</code>' % html.escape(m.group(4)))
        pos = m.end()
    out.append(html.escape(t[pos:]))
    return "".join(out)


def cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--to", default=DEFAULT_TO, help="comma separated recipients")
    ap.add_argument("--subject", default=None, help="override subject (default: first h1)")
    ap.add_argument("--sender", default=DEFAULT_SENDER)
    args = ap.parse_args()

    lines = io.open(args.md, encoding="utf-8").read().replace("\r\n", "\n").split("\n")
    os.makedirs(args.out, exist_ok=True)

    title = ""
    txt, htm = [], []
    i = 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", s)
        if m:
            lvl, raw = len(m.group(1)), m.group(2)
            text = strip_md(raw)
            if lvl == 1:
                if not title:
                    title = text
                txt += ["", text, "=" * min(48, max(12, len(text) * 2))]
                htm.append("<h1>%s</h1>" % inline_html(raw))
            elif lvl == 2:
                txt += ["", text, "-" * min(48, max(12, len(text) * 2))]
                htm.append("<h2>%s</h2>" % inline_html(raw))
            else:
                txt += ["", "### " + text]
                htm.append("<h3>%s</h3>" % inline_html(raw))
            i += 1
            continue
        if s == "---":
            txt.append("")
            htm.append("<hr>")
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            header = cells(rows[0])
            body = [cells(r) for r in rows[1:] if not re.match(r"^\|[\s:\-|]+\|$", r.strip())]
            txt.append("")
            for r in body:
                first = r[0].strip() if r else ""
                if first.startswith("**") and first.endswith("**") and first.count("**") == 2:
                    first = first[2:-2]
                name = strip_md(first)
                url = split_link(first)[1]
                rest = " —— ".join(strip_md(c) for c in r[1:] if c)
                piece = "· %s" % name
                if rest:
                    piece += " —— %s" % rest
                if url:
                    piece += "（%s）" % url
                txt.append(piece)
            th = "".join("<th>%s</th>" % inline_html(h) for h in header)
            trs = []
            for r in body:
                tds = []
                for idx in range(len(header)):
                    cell = r[idx] if idx < len(r) else ""
                    strong = False
                    mm = re.match(r"^\*\*(.+)\*\*$", cell)
                    if mm and "**" not in mm.group(1):
                        strong, cell = True, mm.group(1)
                    name, url = split_link(cell)
                    if url:
                        frag = '<a href="%s">%s</a>' % (
                            html.escape(url, quote=True), html.escape(name))
                        if strong:
                            frag = "<strong>%s</strong>" % frag
                    else:
                        frag = inline_html(cell)
                        if strong:
                            frag = "<strong>%s</strong>" % frag
                    tds.append("<td>%s</td>" % frag)
                trs.append("<tr>%s</tr>" % "".join(tds))
            htm.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
                       % (th, "".join(trs)))
            continue
        if s.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:])
                i += 1
            txt.append("")
            txt.extend("  " + plain(x) for x in items)
            htm.append("<ul>%s</ul>" % "".join(
                "<li>%s</li>" % inline_html(x) for x in items))
            continue
        txt.append(plain(s))
        htm.append("<p>%s</p>" % inline_html(s))
        i += 1

    now = datetime.datetime.now().astimezone()
    stamp = now.strftime("%Y-%m-%d %H:%M (%z)")
    mail_title = args.subject or title
    subject = "转发：" + mail_title
    to_line = args.to.replace(",", "、").replace(";", "、")

    head_txt = ["【AI 代发】", "", "-------- 转发的邮件 --------",
                "发件人：%s" % args.sender,
                "发送时间：%s" % stamp,
                "收件人：%s" % to_line,
                "主题：%s" % mail_title, ""]
    body_txt = "\n".join(head_txt) + "\n" + "\n".join(txt).strip() + "\n"
    io.open(os.path.join(args.out, "mail.txt"), "w", encoding="utf-8", newline="\n").write(body_txt)

    css = ("body{margin:0;padding:16px;background:#fff;font-family:-apple-system,'Segoe UI',"
           "'Microsoft YaHei',sans-serif;font-size:14px;line-height:1.7;color:#222;}"
           ".wrap{max-width:900px;margin:0 auto;}"
           ".badge{display:inline-block;background:#fff3cd;border:1px solid #f0c36d;color:#8a6d3b;"
           "font-weight:700;font-size:13px;padding:3px 10px;border-radius:4px;margin-bottom:10px;}"
           ".fwd{border:1px solid #d6e0ea;border-left:4px solid #8aa7c4;background:#f7fafc;"
           "padding:9px 13px;margin:10px 0 18px;font-size:12.5px;color:#4a5568;line-height:1.65;}"
           "h1{font-size:21px;color:#0b4f8a;border-bottom:3px solid #0b4f8a;padding-bottom:7px;margin:0 0 10px;}"
           "h2{font-size:16px;color:#0b4f8a;border-left:4px solid #0b4f8a;padding-left:9px;margin:22px 0 8px;}"
           "h3{font-size:14px;color:#12588f;margin:16px 0 5px;line-height:1.5;}"
           "ul{padding-left:20px;margin:8px 0;}li{margin:3px 0;}"
           "table{border-collapse:collapse;width:100%;margin:8px 0 14px;font-size:12.5px;}"
           "th{border:1px solid #c9d6e4;background:#e8f0f8;padding:6px 8px;text-align:left;}"
           "td{border:1px solid #d8e2ec;padding:5px 8px;vertical-align:top;}"
           "a{color:#0b4f8a;}code{font-family:Consolas,monospace;font-size:12px;background:#f3f5f8;"
           "color:#a31d1d;padding:1px 4px;border-radius:3px;}hr{border:none;border-top:1px solid #d6e0ea;margin:20px 0;}")
    head_html = (
        '<div class="fwd">'
        '<div><b>-------- 转发的邮件 --------</b></div>'
        '<div><b>发件人：</b>%s</div><div><b>发送时间：</b>%s</div>'
        '<div><b>收件人：</b>%s</div><div><b>主题：</b>%s</div></div>'
        % (args.sender, stamp, to_line, html.escape(mail_title)))
    body_html = "\n".join([
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>%s</title>' % html.escape(mail_title),
        '<style>%s</style></head><body><div class="wrap">' % css,
        '<div class="badge">【AI 代发】</div>',
        head_html,
        "\n".join(htm),
        "</div></body></html>",
    ])
    io.open(os.path.join(args.out, "mail.html"), "w", encoding="utf-8", newline="\n").write(body_html)

    print("subject:", subject)
    print("title  :", title)
    print("stamp  :", stamp)
    print("mail.txt  :", os.path.getsize(os.path.join(args.out, "mail.txt")), "bytes")
    print("mail.html :", os.path.getsize(os.path.join(args.out, "mail.html")), "bytes")


if __name__ == "__main__":
    main()
