import datetime
import os
import re
import shutil
import threading
from flask import Flask, Response, make_response
from flask import request
from flask import jsonify
from flask_cors import CORS, cross_origin
from tools import HtmlHeader
import json
from SMT import SMT
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from sqlalchemy import Column, SmallInteger, create_engine

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}})
connect_str = 'sqlite:///ccsl.db'
# 设置连接数据库的URL
app.config['SQLALCHEMY_DATABASE_URI'] = connect_str
# 设置每次请求结束后会自动提交数据库中的改动
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
#
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
# 查询时会显示原始SQL语句
app.config['SQLALCHEMY_ECHO'] = True
db = SQLAlchemy(app)

class CCSL(db.Model):
    # 定义表名
    __tablename__ = 'CCSL'
    # 定义列对象
    id = Column(db.Integer, primary_key=True,autoincrement=True)
    labname = db.Column(db.String(64))
    bound = db.Column(db.Integer)
    res = db.Column(db.String(64))
    time = db.Column(db.String(64))

    # repr()方法显示一个可读字符串
    def __repr__(self):
        return 'CCSL:%s' % self.id

class LAB(db.Model):
    # 定义表名
    __tablename__ = 'LAB'
    # 定义列对象
    labname = db.Column(db.String(64), primary_key=True)
    date = db.Column(db.DateTime, default=datetime.datetime.now)

    def __repr__(self):
        return 'CCSL:%s' % self.labname

class BLOG(db.Model):
    # 定义表名
    __tablename__ = 'BLOG'
    # 定义列对象
    id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    blogname = db.Column(db.String(64))
    description = db.Column(db.String(200))
    content = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.datetime.now)
    originmd = db.Column(db.Text)

    def __repr__(self):
        return 'BLOG:%s' % self.labname

# db.drop_all()
db.create_all()
# print("+++++++++++++++++++++++++++++++++++++++")
# print(User.query.filter_by(name='zhou').all())


class MyThread(threading.Thread):
    def __init__(self, labid, ccsl, bound):
        super(MyThread, self).__init__()  # 重构run函数必须要写
        self.id = str(labid)
        self.ccslcons = ccsl
        self.bound = bound

    def run(self):
        c1 = CCSL(labname=self.id, res='inprogress', time='0', bound=self.bound)
        db.session.add(c1)
        db.session.commit()

        HtmlHeader(self.id, self.bound)
        smt = SMT(self.ccslcons, labid=self.id, bound=self.bound, period=0, realPeroid=0)
        smt.getAllSchedule()
        time = smt.getTime()
        result = smt.getResult()
        response = smt.getJson()

        la = db.session.query(CCSL).filter_by(labname=self.id, bound=self.bound).first()
        if la:
            la.res = result
            la.time = time
            db.session.add(la)
            db.session.commit()
            j = json.dumps(response)
            jsonpath = "metadata/" + str(self.id) + "/bd-" + str(self.bound) + ".json"
            with open(jsonpath, "w", encoding="utf-8") as f:
                f.write(j)

class doThread(threading.Thread):
    def __init__(self, labid, ccsl, bound, times, gap):
        super(doThread, self).__init__()  # 重构run函数必须要写
        self.id = str(labid)
        self.ccslcons = ccsl
        self.bound = bound
        self.times = times
        self.gap = gap

    def run(self):
        for i in range(0, self.times):
            bd = self.bound + self.gap * i
            que = LAB.query.get(self.id)
            if que:
                MyThread(self.id, self.ccslcons, bd).run()
            else:
                break




@app.route('/')
def hello_world():
    return 'Hello World!'


@app.route('/getMsg', methods=['GET', 'POST'])
def home():
    data = json.loads(request.get_data().decode("utf-8"))
    # print(type(data))
    # print(data.get('ccsl'))
    ccslsrc = data.get('ccsl')
    bound = int(data.get('bound'))
    print(bound)
    with open("ccsl.txt", "w", encoding='utf-8') as f:
        f.write(str(ccslsrc))
        f.close()

    HtmlHeader()
    smt = SMT("ccsl.txt", bound=bound, period=0, realPeroid=0)
    smt.getAllSchedule()
    time = smt.getTime()
    result = smt.getResult()
    # HTMLFooter()
    html = ''
    with open("static/output.html", "r", encoding='utf-8') as f:
        html = f.read()
        f.close()
    response = {
        'ccsl': ccslsrc,
         'result': result,
        'time': time,
        'output': html
    }

    return jsonify(response)


@app.route('/store', methods=['GET', 'POST'])
def store():
    data = json.loads(request.get_data().decode("utf-8"))
    fname = data.get('name')



    bound = (data.get('bound'))
    res = data.get('result')
    time = data.get('time')

    with open("static/output.html", "r", encoding='utf-8') as f:
        output = f.read()
        f.close()
    with open("storedata/" + fname + ".output", "w", encoding='utf-8') as f:
        f.write(output)
        f.close()
    with open("ccsl.txt", "r", encoding='utf-8') as f:
        ccsl = f.read()
        f.close()

    with open("storedata/" + fname + ".ccsl", "w", encoding='utf-8') as f:
        f.write(ccsl)
        f.close()

    c1 = CCSL(name=fname, res=res, time=time, bound=int(bound))
    db.session.add(c1)
    db.session.commit()

    response = {
        'res': "store success"
    }

    return jsonify(response)

@app.route('/Query', methods=['GET', 'POST'])
def query():
    ares = list()
    qres = LAB.query.order_by(LAB.date.desc()).all()
    for item in qres:
        labname = item.labname
        date = item.date
        response = {
        'labname': labname,
        'date': date,
        }
        ares.append(response)
    return jsonify(ares)

@app.route('/Querybd', methods=['GET', 'POST'])
def querybd():
    data = json.loads(request.get_data().decode("utf-8"))
    labname = data.get('labname')
    with open("metadata/" + labname + "/" + labname + ".ccsl", "r", encoding='utf-8') as f:
        ccsl = f.read()
        f.close()
    ares = list()
    qres = db.session.query(CCSL).filter_by(labname=labname).all()
    for item in qres:
        ares.append(item.bound)
    response = {
        'bdlist': ares,
        'ccsl': ccsl,
    }
    return jsonify(response)

@app.route('/QueryOutput', methods=['GET', 'POST'])
def queryoutput():
    data = json.loads(request.get_data().decode("utf-8"))
    labname = data.get('labname')
    bound = data.get('bound')
    qre = db.session.query(CCSL).filter_by(labname=labname, bound=bound).first()
    res = qre.res
    time = qre.time;
    with open("metadata/" + labname + "/" + labname + ".ccsl", "r", encoding='utf-8') as f:
        ccsl = f.read()
        f.close()
    if(res == 'inprogress'):
        response = {
            'ccsl': ccsl,
            'ec': '',
            'output': '还未完成',
            'res': res,
            'time': 'unknown'
        }
        return jsonify(response)

    with open("metadata/"+labname+"/bd-"+str(bound)+".json", "r", encoding='utf-8') as f:
        j = f.read()
        f.close()
    j = json.loads(j);
    with open("metadata/"+labname+"/bd-"+str(bound)+".html", "r", encoding='utf-8') as f:
        h = f.read()
        f.close()
    # h = h.replace("</body></html>","")
    response = {
        'ccsl': ccsl,
        'ec': j,
        'output': h,
        'res': res,
        'time': time
    }

    return jsonify(response)



@app.route('/blogup', methods=['GET', 'POST'])
def blogup():
    data = json.loads(request.get_data().decode("utf-8"))
    content = data.get('content')
    desc = data.get('desc')
    title = data.get('title')
    originmd = data.get('ori')
    blog = BLOG(blogname=title, content=content, description=desc, originmd=originmd)
    db.session.add(blog)
    db.session.commit()
    return jsonify("up success")

#用户获取具体blog id的内容
@app.route('/queryblogcontent', methods=['GET', 'POST'])
def blogcontent():
    data = json.loads(request.get_data().decode("utf-8"))
    id = data.get('id')
    que = BLOG.query.get(id)
    res = {
        'content': 'fail'
    }
    if que:
        res = {
            'content': que.content,
            'ori': que.originmd
        }
    return jsonify(res)

#用户获取blog列表
@app.route('/queryblog', methods=['GET', 'POST'])
def bloglist():
    ares = list()
    qres = BLOG.query.order_by(BLOG.date.desc()).all()
    for item in qres:
        id = item.id
        date = item.date
        desc = item.description
        title = item.blogname
        response = {
        'id': id,
        'date': date,
        'title': title,
        'desc': desc
        }
        ares.append(response)
    return jsonify(ares)

@app.route('/do', methods=['GET', 'POST'])
def test():
    data = json.loads(request.get_data().decode("utf-8"))
    ccslsrc = data.get('ccsl')
    bound = int(data.get('bound'))
    labname= data.get('labname')
    times = int(data.get('times'))
    gap = int(data.get('gap'))

    qres = LAB.query.get(labname)
    print(qres)
    if(qres):
        return jsonify("LabName Conflict")
    else:
        labpath = "metadata/" + labname;
        print(labpath)
        os.makedirs(labpath)
        ccslpath = labpath + "/" + labname + ".ccsl"
        with open(ccslpath, "w+", encoding="utf-8") as f:
            f.write(ccslsrc)
        lab = LAB(labname=labname)
        db.session.add(lab)
        db.session.commit()
        doThread(labname, ccslsrc, bound, times, gap).start()

        return jsonify("ok " +str(times)+" lab in progress")

#清空垃圾图片
@app.route('/clearoutpic', methods=['GET', 'POST'])
def deletenopic():
    lll = []
    for files in os.walk("blog/pic/"):
        lll = files[2]
    print(lll)
    la = db.session.query(BLOG).all()
    for item in la:
        list = re.findall("<img src=\"blog/pic/(.+?)\" ", str(item.content))
        for f in list:
            if(f in lll):
                lll.remove(f)
    for f in lll:
        os.remove("blog/pic/"+f)

    return jsonify(lll)

#删除某个博客
@app.route('/deleteblog', methods=['GET', 'POST'])
def deleteblog():
    data = json.loads(request.get_data().decode("utf-8"))
    id = data.get('id')
    que = BLOG.query.get(id)
    if que:
        list = re.findall("<img src=\"(.+?)\" ", str(que.content))
        for f in list:
            if os.path.exists(f):
                os.remove(f)
        db.session.delete(que)
        db.session.commit()
        response = {
            'r': 'Success !'
            }
    else:
        response = {
            'r': 'Failed!'
            }

    return jsonify(response)



@app.route('/DeleteLab', methods=['GET', 'POST'])
def deletelab():
    data = json.loads(request.get_data().decode("utf-8"))
    labname = data.get('labname')
    que = LAB.query.get(labname)
    if que:
        db.session.delete(que)
        db.session.commit()
        qres = db.session.query(CCSL).filter_by(labname=labname).all()
        if qres:
            for item in qres:
                db.session.delete(item)
                db.session.commit()
            shutil.rmtree('metadata/'+labname)
            response = {
                'r': True
            }
        else:
            response = {
                'r': False
            }
    else:
        response = {
            'r': False
        }

    return jsonify(response)

@app.route('/blog/uploadblogpic', methods=['POST'])
def uploadpic():
    file = request.files.get('editormd-image-file')
    print(file)
    if not file:
        result = {
            'success': 0,
            'message': "失败"}
    else:
        ext = str(os.path.splitext(file.filename)[1])

        filename = str(datetime.datetime.now().strftime('%Y%m%d%H%M%S')) + ext
        print(ext)
        file.save(os.path.join('blog/pic', filename))
        result = {
            'success': 1,
            'message': "成功",
            'url': 'blog/pic/' + filename}

    print(result)
    return result

@app.route('/blog/pic/<name>', methods=['GET'])
def image(name):
     with open(os.path.join('blog/pic/', name), 'rb') as f:
         resp= Response(f.read(), mimetype="image/jpeg")
     return resp

# 启动运行
if __name__ == '__main__':
    app.run()  # 这样子会直接运行在本地服务器，也即是 localhost:5000
# app.run(host='your_ip_address') # 这里可通过 host 指定在公网IP上运行
