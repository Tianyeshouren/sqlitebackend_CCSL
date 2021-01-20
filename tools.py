def HtmlHeader(id,bd):
    # html = "<html><body><style type=\"text/css\">\n"
    html = "<style type=\"text/css\">\n"
    for each in open("output.css", "r").readlines():
        html += each
    html += "</style>"
    with open("metadata/"+id+"/bd-" + str(bd)+".html", "w", encoding="utf-8") as f:
        f.write(html)
        f.flush()
        f.close()

def HTMLFooter(id,bd):
    html = "</body></html>"
    with open("metadata/"+id+"/bd-" + str(bd)+".html", "a+", encoding="utf-8") as f:
        f.write(html)
        f.flush()
        f.close()

def is_number(s):
    return set(s).issubset(set("1234567890"))
