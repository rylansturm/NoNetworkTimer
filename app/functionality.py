import datetime
import configparser
from app.schedule import Schedule
import os

raspi = os.sys.platform == 'linux'

if raspi:
    from app.lights import Light


c = configparser.ConfigParser()
c.read('setup.ini')


class PCT:
    plan_cycle_time = int(c['Values']['pct'])
    new = ''
    adjusted = False
    adjust = False


class Partsper:
    partsper = int(c['Values']['partsper'])
    new = ''
    adjusted = False
    adjust = False


class Timer:
    window = 3
    tCycle = 0
    mark = datetime.datetime.now()
    andons = 0
    responded = 0
    color = 'light grey'
    avg_cycle = 0
    late = 0
    early = 0
    on_target = 0
    past_10 = ["00:00:00"]

    @staticmethod
    def get_ahead():
        expected = Plan.block_time_elapsed() // (Partsper.partsper * PCT.plan_cycle_time)
        return int(Plan.total_cycles() - expected)


class Plan:
    schedule = Schedule()
    new_shift = True
    expected_cycles = 0
    block = 0

    @staticmethod
    def total_cycles():
        return Timer.late + Timer.early + Timer.on_target

    @staticmethod
    def block_remaining_time():
        return (Plan.schedule.end[Plan.block-1] - now()).total_seconds()

    @staticmethod
    def block_time_elapsed():
        return (now() - Plan.schedule.start[Plan.block-1]).total_seconds()


def now():
    return datetime.datetime.now()


def andon(btn):
    if btn == 'Andon':
        Timer.andons += 1
    if btn == 'Respond':
        Timer.responded = Timer.andons


def cycle():
    if (now() - Timer.mark).total_seconds() > 2:
        window = Timer.window * Partsper.partsper
        if Timer.tCycle < -window:
            Timer.late += 1
        elif Timer.tCycle > window:
            Timer.early += 1
        else:
            Timer.on_target += 1
        Timer.past_10.append(countdown_format(int((now() - Timer.mark).total_seconds())))
        if len(Timer.past_10) > 10:
            Timer.past_10 = Timer.past_10[1:]
        Timer.mark = now()


def adjust_cycles(btn):
    exec('Timer.%s += 1' % btn)


def set_PCT(btn):
    if btn == 'OK_PCT':
        PCT.adjust = True
    elif btn == 'Back_PCT':
        PCT.adjusted = True
        PCT.new = '-'
    else:
        PCT.adjusted = True
        PCT.new = btn[0]


def set_partsper(btn):
    if btn == 'OK_partsper':
        Partsper.adjust = True
    elif btn == 'Back_partsper':
        Partsper.adjusted = True
        Partsper.new = '-'
    else:
        Partsper.adjusted = True
        Partsper.new = btn[0]


def screen_color():
    window = Timer.window * Partsper.partsper
    if Timer.tCycle > window:
        Timer.color = 'light grey'
    elif -window <= Timer.tCycle <= window:
        Timer.color = 'yellow'
    else:
        Timer.color = 'red'


def run_lights():
    if Timer.responded != Timer.andons:
        Light.set_all(1, 0, 0)
    else:
        Light.set_all(0, 0, 1)


def new_block():
    start = Plan.schedule.start[Plan.block - 1]
    end = Plan.schedule.end[Plan.block - 1]
    available_time = (end - start).total_seconds()
    Timer.on_target = 0
    Timer.late = 0
    Timer.early = 0
    Plan.expected_cycles = int(available_time // (PCT.plan_cycle_time * Partsper.partsper))
    Timer.mark = now()


def get_tCycle():
    Timer.tCycle = (PCT.plan_cycle_time * Partsper.partsper) - int((now() - Timer.mark).total_seconds())
    return Timer.tCycle


def get_andons():
    if Timer.responded != Timer.andons:
        return '%s + %s' % (Timer.responded, Timer.andons - Timer.responded)
    else:
        return Timer.andons


def schedule_format(time):
    return datetime.datetime.strftime(time, '%I:%M %p')


def countdown_format(seconds: int):
    """ takes seconds and returns ":SS", "MM:SS", or "HH:MM:SS" """
    sign = -1 if seconds < 0 else 1
    seconds = seconds * sign
    sign_label = '-' if sign < 0 else ''
    hours, minutes = divmod(seconds, 3600)
    minutes, seconds = divmod(minutes, 60)
    hour_label = '%sh:%02d' % (hours, minutes)
    minute_label = '%s:%02d' % (minutes, seconds)
    second_label = sign_label + ':%02d' % seconds
    return seconds if hours < 0 else hour_label if hours else minute_label if minutes else second_label


def write_schedule(app):
    for block in [1, 2, 3, 4]:
        start = Plan.schedule.start[block - 1]
        end = Plan.schedule.end[block - 1]
        app.setLabel('start%s' % block, schedule_format(start))
        app.setLabel('end%s' % block, schedule_format(end))


def adjust_schedule(btn):
    delta = datetime.timedelta(minutes=5)
    time = btn[0]
    direction = btn[-2]
    block = int(btn[-3])
    if time == 's':
        Plan.schedule.start[block - 1] += delta if direction == 'U' else -delta
    elif time == 'e':
        Plan.schedule.end[block - 1] += delta if direction == 'U' else -delta
    Plan.new_shift = True
    new_block()


def update_default(btn):
    c = configparser.ConfigParser()
    c.read('schedules.ini')
    start = ', '.join([datetime.datetime.strftime(time, '%H%M') for time in Plan.schedule.start])
    end = ', '.join([datetime.datetime.strftime(time, '%H%M') for time in Plan.schedule.end])
    c[Plan.schedule.shift]['start'] = start
    c[Plan.schedule.shift]['end'] = end
    with open('schedules.ini', 'w') as configfile:
        c.write(configfile)


def function(app):
    def counting():
        if raspi:
            run_lights()
        if now() > Plan.schedule.schedule()[-1]:
            Plan.new_shift = True
            Plan.schedule = Schedule()
        if Plan.block != Plan.schedule.get_block():
            Plan.block = Plan.schedule.get_block()
            new_block()
        Timer.tCycle = get_tCycle()
        if Timer.past_10[-1] != app.getOptionBox('past_10'):
            app.changeOptionBox('past_10', Timer.past_10)
            app.setOptionBox('past_10', Timer.past_10[-1])
        if now() < Plan.schedule.start[Plan.block-1]:
            label = 'Shift: %s\tDate: %s\n\n\tAvailable Time: %s\n\nPCT: %s\t\tParts per Cycle: %s' % (
                Plan.schedule.shift, datetime.date.today(),
                Plan.schedule.available_time(), PCT.plan_cycle_time, Partsper.partsper)
            app.setLabel('tCycle', label)
            app.getLabelWidget('tCycle').config(font='arial 48')
            app.setLabel('ahead', 'Ahead: N/A')
            Timer.color = 'green'
        elif now() < Plan.schedule.end[Plan.block-1]:
            app.setLabel('tCycle', countdown_format(Timer.tCycle))
            app.getLabelWidget('tCycle').config(font='arial 148')
            screen_color()
            ahead = Timer.get_ahead()
            if ahead >= 0:
                ahead_label = 'Ahead: %s' % ahead
            else:
                ahead_label = 'Behind: %s' % -ahead
            app.setLabel('ahead', ahead_label)
        else:
            app.setLabel('tCycle', '%s / %s' % (Plan.total_cycles(), Plan.expected_cycles))
            app.getLabelWidget('tCycle').config(font='arial 64')
            Timer.color = 'green'
            app.setLabel('ahead', 'Ahead: N/A')
        if Timer.color != app.getLabelBg('tCycle'):
            app.setLabelBg('tCycle', Timer.color)
            print('color change: %s' % Timer.color)
        try:
            app.setLabel('consistency', 'Consistency: %s%%' % int((Timer.on_target / Plan.total_cycles()) * 100))
        except ZeroDivisionError:
            app.setLabel('consistency', 'Consistency: N/A')
        app.setLabel('late', 'Late: %s' % Timer.late)
        app.setLabel('early', 'Early: %s' % Timer.early)
        app.setLabel('on_target', 'On Time: %s' % Timer.on_target)
        app.setLabel('andons', get_andons())
        if Plan.new_shift:
            write_schedule(app)
            Plan.new_shift = False
            Timer.andons = 0
            Timer.responded = 0

        app.setLabel('PCT', PCT.plan_cycle_time)
        if PCT.adjusted:
            new_pct = app.getEntry('new_pct')
            if PCT.new == '-':
                new_pct = new_pct[0:-1]
            else:
                new_pct += PCT.new
            app.setEntry('new_pct', new_pct)
            PCT.adjusted = False
        if PCT.adjust:
            if app.getEntry('new_pct') != '':
                PCT.plan_cycle_time = int(app.getEntry('new_pct'))
                app.setEntry('new_pct', '')
                available_time = (Plan.schedule.end[Plan.block-1] - Plan.schedule.start[Plan.block-1]).total_seconds()
                Plan.expected_cycles = int(available_time // (PCT.plan_cycle_time * Partsper.partsper))
            PCT.adjust = False
            c = configparser.ConfigParser()
            c.read('setup.ini')
            c['Values']['pct'] = str(PCT.plan_cycle_time)
            with open('setup.ini', 'w') as configfile:
                c.write(configfile)

        app.setLabel('partsper', Partsper.partsper)
        if Partsper.adjusted:
            new_partsper = app.getEntry('new_partsper')
            if Partsper.new == '-':
                new_partsper = new_partsper[0:-1]
            else:
                new_partsper += Partsper.new
            app.setEntry('new_partsper', new_partsper)
            Partsper.adjusted = False
        if Partsper.adjust:
            if app.getEntry('new_partsper') != '':
                Partsper.partsper = int(app.getEntry('new_partsper'))
                app.setEntry('new_partsper', '')
                available_time = (Plan.schedule.end[Plan.block-1] - Plan.schedule.start[Plan.block-1]).total_seconds()
                Plan.expected_cycles = int(available_time // (PCT.plan_cycle_time * Partsper.partsper))
            Partsper.adjust = False
            c = configparser.ConfigParser()
            c.read('setup.ini')
            c['Values']['partsper'] = str(Partsper.partsper)
            with open('setup.ini', 'w') as configfile:
                c.write(configfile)
    app.registerEvent(counting)
    app.setPollTime(50)
    app.bindKey('<space>', cycle)
    app.bindKey('1', cycle)
    return app
