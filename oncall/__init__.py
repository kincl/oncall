from flask import Flask, request, render_template, abort, json, Response, g
from flask.ext.sqlalchemy import SQLAlchemy
from jinja2 import TemplateNotFound
from datetime import date, timedelta

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'

db = SQLAlchemy(app)

from oncall.models import Event
from oncall.models import User
from oncall.models import Team

ROLES = ['Primary',
         'Secondary']

def _str_to_date(date_str):
    """ converts string of 2014-04-13 to Python date """
    return date(*[int(n) for n in str(date_str).split('-')])

def _get_events_for_dates(start_date, end_date, exclude_event = None):
    start  = _str_to_date(start_date)
    end = _str_to_date(end_date if end_date else start_date)
    events_start = Event.query.filter(start >= Event.start,
                                      start <= Event.end,
                                      Event.id != exclude_event,
                                      Event.team_slug == g.team)
    events_end = Event.query.filter(end >= Event.start,
                                    end <= Event.end,
                                    Event.id != exclude_event,
                                    Event.team_slug == g.team)
    events_inside = Event.query.filter(start <= Event.start,
                                       end >= Event.end,
                                       Event.id != exclude_event,
                                        Event.team_slug == g.team)

    return events_start.union(events_end, events_inside).all()


def _can_add_event(start_date, end_date, exclude_event = None):
    """ Given a start and end date, make sure that there are not more
        than two events. """

    events_all = _get_events_for_dates(start_date, end_date, exclude_event)

    one_day = timedelta(1)

    i = _str_to_date(start_date)
    while i != _str_to_date(end_date if end_date else start_date) + one_day:
        count = 0
        for e in events_all:
            if i >= e.start and i <= e.end:
                count += 1
        if count >= len(ROLES):
            return False
        i += one_day
    return True

def _is_role_valid(eventid, new_role, start_date = None, end_date = None):
    """ Can we change the of the given event to new_role, look up
        the event and see if there are any events that have that 
        role already """
    e = Event.query.filter_by(id=eventid).first()
    events = _get_events_for_dates(start_date if start_date else e.start,
                                   end_date if end_date else e.end,
                                   exclude_event=eventid)
    flag = True
    for event in events:
        if event.role == new_role:
            flag = False
    return flag

def _other_role(start_role):
    """ TODO: make it work for more than two roles """
    for role in ROLES:
        if role != start_role:
            return role

@app.route('/', defaults={'page': 'index'})
@app.route('/<page>')
def show(page):
    try:
        return render_template('%s.html' % page)
    except TemplateNotFound:
        abort(404)

@app.route('/get_events')
def get_events():
    return Response(json.dumps([e.to_json() for e in Event.query.filter_by(team_slug=request.args.get('team')).all()]),
           mimetype='application/json')

@app.route('/get_teams')
def get_teams():
    return Response(json.dumps([t.to_json() for t in Team.query.all()]),
                    mimetype='application/json')

@app.route('/get_team_members/<team>')
def get_team_members(team):
    return Response(json.dumps([u.to_json() for u in User.query.filter_by(team_slug=team).all()]),
                    mimetype='application/json')

@app.route('/get_roles')
def get_roles():
    return Response(json.dumps(ROLES),
                    mimetype='application/json')

@app.route('/create_event', methods=['POST'])
def create_event():
    g.team = request.form.get('team')
    if _can_add_event(request.form.get('start'), request.form.get('end')):
        events = _get_events_for_dates(request.form.get('start'), request.form.get('end'))
        newe = Event(request.form.get('username'),
                     request.form.get('team'),
                     ROLES[0] if events == [] else _other_role(events[0].role),
                     _str_to_date(request.form.get('start')))

        db.session.add(newe)
        db.session.commit()
        return Response(json.dumps({'result': 'success'}),
                        mimetype='application/json')
    else:
        return Response(json.dumps({'result': 'failure'}),
                        mimetype='application/json')

@app.route('/update_event/<eventid>', methods=['POST'])
def update_event(eventid):
    e = Event.query.filter_by(id=eventid).first()
    g.team = e.team_slug
    if request.form.get('start'):
        if _can_add_event(request.form.get('start'), request.form.get('end'), exclude_event=eventid):
            if _is_role_valid(eventid, e.role, request.form.get('start'), request.form.get('end')):
                e.start = _str_to_date(request.form.get('start'))
                e.end = _str_to_date(request.form.get('end') if request.form.get('end') else request.form.get('start'))
            elif _is_role_valid(eventid, _other_role(e.role), request.form.get('start'), request.form.get('end')):
                e.start = _str_to_date(request.form.get('start'))
                e.end = _str_to_date(request.form.get('end') if request.form.get('end') else request.form.get('start'))
                e.role = _other_role(e.role)

    if request.form.get('role'):
        if _is_role_valid(eventid, request.form.get('role')):
            e.role = request.form.get('role')

    if request.form.get('user_username'):
        e.user_username = request.form.get('user_username')
        
    if db.session.commit():
        return Response(json.dumps({'result': 'success'}),
                        mimetype='application/json')
    else:
        return Response(json.dumps({'result': 'failure'}),
                        mimetype='application/json')

@app.route('/delete_event/<eventid>', methods=['POST'])
def delete_event(eventid):
    e = Event.query.filter_by(id=eventid).first()
    db.session.delete(e)
    db.session.commit()
    return Response(json.dumps({'result': 'success'}),
                    mimetype='application/json')


