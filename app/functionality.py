"""
Basic functionality of the timer is very simple:
    1.  What is planned cycle time (PCT)?
    2.  How many parts does this sequence produce per cycle (Partsper)?
            Sequence time is PCT * Partsper
    3.  The timer counts down from the expected sequence time and restarts when the pedal is pushed.
        If the expectation is missed, the timer will continue to count into the negative to show total missed time.
    4.  At the end of the planned 'available time' the timer will automatically stop and display measurables.
        Timer will start again with the new block

Additional functionality:
    **  Andons can be signaled and dismissed visually, and a cumulative count is kept
    **  Stores end-of-shift data in csv file, displays last 3 shifts on 'History' tab
    **  Live metrics for:
        * Number of cycles ahead/behind
        * Total number of cycles that were late, on target, or early

Functions for the takt timer module are separated into 5 classes:

PCT:
    Everything related to the planned cycle time
Partsper:
    Everything related to the parts delivered per cycle
Andon:
    Everything related to visually signaling andon, including the operation of the LED
Plan:
    Variables and functions that deal with the scheduled start/stop times and how they operate
Timer:
    The main functionality and counting mechanisms of the timer
"""

# imports
import datetime
import configparser
from app.schedule import Schedule  # see schedule.py for documentation
import os


# overly simple boolean to determine if we are running on windows or a raspberry pi
# functions that should not be ran while testing on Windows will check this variable first (ie shut_down, run_lights)

raspi = os.sys.platform == 'linux'
if raspi:
    from app.lights import Light  # see lights.py for documentation


# configparser object to read initialization file (setup.ini)
# partsper and pct are stored here so the system will not forget after being restarted

c = configparser.ConfigParser()
c.read('setup.ini')


class PCT:
    """pct -> int; number of seconds planned for cycling each part through flow"""
    planned_cycle_time = int(c['Values']['pct'])
    catch_up_pct = planned_cycle_time

    # new/adjusted/adjust are read by the gui to determine if/when to write changes
    new = ''
    adjusted = False
    adjust = False

    @staticmethod
    def sequence_time():
        return PCT.planned_cycle_time * Partsper.partsper

    @staticmethod
    def set_PCT(btn):
        if btn == 'OK_PCT':
            PCT.adjust = True
        elif btn == 'Back_PCT':
            PCT.adjusted = True
            PCT.new = '-'
        else:
            PCT.adjusted = True
            PCT.new = btn[0]

    @staticmethod
    def catch_up(btn):
        Timer.show_catch_up = True

    @staticmethod
    def cycles_until_caught_up():
        ahead = (Timer.total_block_cycles() * PCT.sequence_time()) - Plan.block_time_elapsed()
        diff = (PCT.catch_up_pct - PCT.planned_cycle_time) * Partsper.partsper
        try:
            return int(ahead / diff)
        except ZeroDivisionError:
            return 'infinite'


class Partsper:
    """partsper -> int; the number of parts this sequence produces in one cycle"""
    partsper = int(c['Values']['partsper'])

    # new/adjusted/adjust are read by the gui to determine if/when to write changes
    new = ''
    adjusted = False
    adjust = False

    @staticmethod
    def set_partsper(btn):
        if btn == 'OK_partsper':
            Partsper.adjust = True
        elif btn == 'Back_partsper':
            Partsper.adjusted = True
            Partsper.new = '-'
        else:
            Partsper.adjusted = True
            Partsper.new = btn[0]


class Andon:
    """ andons -> int; The number of times an operator has signaled an abnormality
        only two buttons interact with the andon system, 'Andon' and 'Respond' """
    andons = 0
    responded = 0  # used to show how many andons the team leader has already responded to

    @staticmethod
    def andon(btn):
        if btn == 'Andon':  # operator signals andon, changing LED to red
            Andon.andons += 1
        if btn == 'Respond':  # team leader responds to andon and resets andon LED
            Andon.responded = Andon.andons

    @staticmethod
    def run_lights():
        if Andon.responded != Andon.andons:
            Light.set_all(1, 0, 0)
        else:
            Light.set_all(0, 0, 1)

    @staticmethod
    def get_andons():
        if Andon.responded != Andon.andons:
            return '%s + %s' % (Andon.responded, Andon.andons - Andon.responded)
        else:
            return Andon.andons


class Timer:
    window = 3
    tCycle = 0
    mark = datetime.datetime.now()
    color = 'light grey'
    avg_cycle = 0
    late = 0
    early = 0
    on_target = 0
    total_shift_cycles = 0
    expected_cycles = 0
    past_10 = ["00:00:00"]
    update_history = False
    block_history = {}
    show_catch_up = False
    hide_catch_up = True
    catch_up_mode = False

    @staticmethod
    def get_tCycle():
        if not Timer.catch_up_mode:
            Timer.tCycle = PCT.sequence_time() - int((Plan.now() - Timer.mark).total_seconds())
        else:
            Timer.tCycle = PCT.sequence_time() - int((Plan.now() - Timer.mark).total_seconds())
        return Timer.tCycle

    @staticmethod
    def set_catch_up(btn):
        if btn == 'OK':
            Timer.catch_up_mode = True
            Timer.hide_catch_up = True

    @staticmethod
    def countdown_format(seconds: int):
        """ takes int (seconds) and returns str (":SS", "MM:SS", or "HH:MM:SS") """
        sign = -1 if seconds < 0 else 1
        seconds = seconds * sign
        sign_label = '-' if sign < 0 else ''
        hours, minutes = divmod(seconds, 3600)
        minutes, seconds = divmod(minutes, 60)
        hour_label = '%sh:%02d' % (hours, minutes)
        minute_label = '%s:%02d' % (minutes, seconds)
        second_label = sign_label + ':%02d' % seconds
        return seconds if hours < 0 else hour_label if hours else minute_label if minutes else second_label

    @staticmethod
    def get_ahead():
        expected = Plan.block_time_elapsed() // (Partsper.partsper * PCT.planned_cycle_time)
        return int(Timer.total_block_cycles() - expected)

    @staticmethod
    def cycle():
        if (Plan.now() - Timer.mark).total_seconds() > 2:
            window = Timer.window * Partsper.partsper
            if Timer.tCycle < -window:
                Timer.late += 1
            elif Timer.tCycle > window:
                Timer.early += 1
            else:
                Timer.on_target += 1
            Timer.past_10.append(Timer.countdown_format(int((Plan.now() - Timer.mark).total_seconds())))
            if len(Timer.past_10) > 10:
                Timer.past_10 = Timer.past_10[1:]
            Timer.mark = Plan.now()
            Timer.update_history = True
            Timer.total_shift_cycles += 1

    @staticmethod
    def total_block_cycles():
        return Timer.late + Timer.early + Timer.on_target

    @staticmethod
    def adjust_cycles(btn):
        exec('Timer.%s += 1' % btn)
        Timer.total_shift_cycles += 1

    @staticmethod
    def screen_color():
        window = Timer.window * Partsper.partsper
        if Timer.tCycle > window:
            Timer.color = 'light grey'
        elif -window <= Timer.tCycle <= window:
            Timer.color = 'yellow'
        else:
            Timer.color = 'red'

    @staticmethod
    def shut_down(btn):
        if raspi:
            os.system('sudo shutdown now')
        else:
            print('This would normally shut down a Raspberry Pi. Windows is immune!')


class Plan:
    schedule = Schedule()
    shift = schedule.shift_select()
    new_shift = True
    schedule_adjusted = False
    block = 0
    block_time = 0
    total_time = 0

    @staticmethod
    def block_remaining_time():
        return (Plan.schedule.end[Plan.block-1] - Plan.now()).total_seconds()

    @staticmethod
    def block_time_elapsed():
        return (Plan.now() - Plan.schedule.start[Plan.block-1]).total_seconds()

    @staticmethod
    def new_block():
        start = Plan.schedule.start[Plan.block - 1]
        end = Plan.schedule.end[Plan.block - 1]
        available_time = (end - start).total_seconds()
        Timer.on_target = 0
        Timer.late = 0
        Timer.early = 0
        Timer.expected_cycles = int(available_time // PCT.sequence_time())

    @staticmethod
    def now():
        return datetime.datetime.now()

    @staticmethod
    def schedule_format(time):
        return datetime.datetime.strftime(time, '%I:%M %p')

    @staticmethod
    def time_format(time=None):
        if not time:
            return datetime.datetime.strftime(Plan.now(), '%I:%M:%S %p')
        else:
            return datetime.datetime.strftime(time, '%I:%M:%S %p')

    @staticmethod
    def write_schedule(app):
        Plan.total_time = 0
        for block in [1, 2, 3, 4]:
            start = Plan.schedule.start[block - 1]
            end = Plan.schedule.end[block - 1]
            time = int((end-start).total_seconds())
            Plan.total_time += time
            app.setLabel('start%s' % block, Plan.schedule_format(start))
            app.setLabel('end%s' % block, Plan.schedule_format(end))
            app.setLabel('block%sTime' % block, '%s seconds' % time)
        app.setLabel('availableTime', '%s Total Seconds' % Plan.total_time)

    @staticmethod
    def adjust_schedule(btn):
        shifts = {'Grave':  (23, 7),
                  'Day':    (7, 15),
                  'Swing':  (15, 23)
                  }
        delta = datetime.timedelta(minutes=5)
        time = btn[0]
        direction = btn[-2]
        block = int(btn[-3]) - 1
        if time == 's':
            Plan.schedule.start[block] += delta if direction == 'U' else -delta
            if Plan.schedule.start[block] > Plan.schedule.end[block]:
                Plan.schedule.start[block] = Plan.schedule.end[block]
            if block != 0 and Plan.schedule.start[block] < Plan.schedule.end[block-1]:
                Plan.schedule.start[block] += delta
            if Plan.schedule.start[block].hour < shifts[Plan.shift][0]:
                if Plan.shift != 'Grave':
                    Plan.schedule.start[block] += delta
                elif Plan.schedule.start[block].hour == 22:
                    Plan.schedule.start[block] += delta
        elif time == 'e':
            Plan.schedule.end[block] += delta if direction == 'U' else -delta
            if Plan.schedule.start[block] > Plan.schedule.end[block]:
                Plan.schedule.end[block] = Plan.schedule.start[block]
            if block != 3 and Plan.schedule.end[block] > Plan.schedule.start[block+1]:
                Plan.schedule.end[block] -= delta
            if Plan.schedule.end[block].hour == shifts[Plan.shift][1] and Plan.schedule.end[block].minute > 0:
                if Plan.shift != 'Grave':
                    Plan.schedule.end[block] -= delta
                elif Plan.schedule.end[block].hour == 7 and Plan.schedule.end[block].minute > 0:
                    Plan.schedule.end[block] -= delta
        Plan.schedule_adjusted = True
        Plan.block_time = Plan.schedule.block_time()

    @staticmethod
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
            Andon.run_lights()
        if Plan.now() > Plan.schedule.schedule()[-1]:
            Plan.new_shift = True
            Plan.schedule = Schedule()
            Plan.shift = Plan.schedule.shift_select()
        if Plan.block != Plan.schedule.get_block():
            if Plan.block != 0:
                Timer.block_history['block%s' % Plan.block] = '%s/%s' % (
                    Timer.total_block_cycles(), Timer.expected_cycles)
            Plan.block = Plan.schedule.get_block()
            Plan.block_time = Plan.schedule.block_time()
            Plan.new_block()
            Timer.mark = Plan.now()
        Timer.tCycle = Timer.get_tCycle()
        if Timer.update_history:
            app.changeOptionBox('past_10', Timer.past_10)
            app.setOptionBox('past_10', Timer.past_10[-1])
            Timer.update_history = False
        if Plan.now() < Plan.schedule.start[Plan.block-1]:
            label = 'Shift: %s\tDate: %s\n\n\tAvailable Time: %s\n\nPCT: %s\t\tParts per Cycle: %s' % (
                Plan.schedule.shift, datetime.date.today(),
                Plan.schedule.available_time(), PCT.planned_cycle_time, Partsper.partsper)
            app.setLabel('tCycle', label)
            app.getLabelWidget('tCycle').config(font='arial 20')
            app.setLabel('ahead', 'Ahead: N/A')
            Timer.color = 'green'
        elif Plan.now() < Plan.schedule.end[Plan.block-1]:
            app.setLabel('tCycle', Timer.countdown_format(Timer.tCycle))
            app.getLabelWidget('tCycle').config(font='arial 148')
            Timer.screen_color()
            ahead = Timer.get_ahead()
            current_expected = int(Plan.block_time_elapsed() // (Partsper.partsper * PCT.planned_cycle_time))
            if ahead >= 0:
                ahead_label = 'Ahead: %s (%s/%s)' % (ahead, Timer.total_block_cycles(), current_expected)
                Timer.catch_up_mode = False
            else:
                ahead_label = 'Behind: %s (%s/%s)' % (-ahead, Timer.total_block_cycles(), current_expected)
            app.setLabel('ahead', ahead_label)
        else:
            app.setLabel('tCycle', '%s / %s' % (Timer.total_block_cycles(), Timer.expected_cycles))
            app.getLabelWidget('tCycle').config(font='arial 64')
            Timer.color = 'green'
            app.setLabel('ahead', 'BREAK')
        if Timer.color != app.getLabelBg('tCycle'):
            app.setLabelBg('tCycle', Timer.color)
            print('color change: %s' % Timer.color)
        try:
            app.setLabel('consistency', Plan.time_format())
        except ZeroDivisionError:
            app.setLabel('consistency', Plan.time_format())
        app.setLabel('late', 'Late: %s' % Timer.late)
        app.setLabel('early', 'Early: %s' % Timer.early)
        app.setLabel('on_target', 'On Time: %s' % Timer.on_target)
        app.setLabel('andons', Andon.get_andons())
        if Plan.schedule_adjusted:
            Plan.write_schedule(app)
            Plan.schedule_adjusted = False
        if Plan.new_shift:
            Plan.write_schedule(app)
            Plan.new_shift = False
            Timer.andons = 0
            Timer.responded = 0
            Timer.total_shift_cycles = 0

        app.setLabel('PCT', PCT.planned_cycle_time)
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
                PCT.planned_cycle_time = int(app.getEntry('new_pct'))
                app.setEntry('new_pct', '')
                available_time = (Plan.schedule.end[Plan.block-1] - Plan.schedule.start[Plan.block-1]).total_seconds()
                Timer.expected_cycles = int(available_time // PCT.sequence_time())
            PCT.adjust = False
            c = configparser.ConfigParser()
            c.read('setup.ini')
            c['Values']['pct'] = str(PCT.planned_cycle_time)
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
                Timer.expected_cycles = int(available_time // PCT.sequence_time())
            Partsper.adjust = False
            c = configparser.ConfigParser()
            c.read('setup.ini')
            c['Values']['partsper'] = str(Partsper.partsper)
            with open('setup.ini', 'w') as configfile:
                c.write(configfile)
        PCT.catch_up_pct = app.getScale('catch_up_scale')
        app.setScaleRange('catch_up_scale', int(PCT.planned_cycle_time * .6), PCT.planned_cycle_time,
                          curr=PCT.catch_up_pct)
        app.showScaleValue('catch_up_scale', show=True)
        app.setScaleIncrement('catch_up_scale', 1)
        app.setLabel('cycles_until_caught_up', '%s sec/part will catch\n  you up in %s cycles' %
                     (PCT.catch_up_pct, PCT.cycles_until_caught_up()))
        if Timer.show_catch_up:
            app.setScale('catch_up_scale', PCT.planned_cycle_time)
            app.showSubWindow('Catch Up?')
            Timer.show_catch_up = False
        if Timer.hide_catch_up:
            app.hideSubWindow('Catch Up?')
            Timer.hide_catch_up = False
        if Timer.catch_up_mode:
            app.setStatusbar('Catch Up Mode - PCT %s * %s part(s)' % (PCT.catch_up_pct, Partsper.partsper), 0)
        else:
            app.setStatusbar('PCT %s * %s part(s) = %s' %
                             (PCT.planned_cycle_time, Partsper.partsper, Timer.countdown_format(PCT.sequence_time())),
                             0)
        app.setStatusbar('Block Cycles: %s/%s' % (Timer.total_block_cycles(),
                                                  int(Plan.block_time // PCT.sequence_time())),
                         1)
        app.setStatusbar('Shift Cycles: %s/%s' % (Timer.total_shift_cycles,
                                                  int(Plan.schedule.available_time() // PCT.sequence_time())),
                         2)
    app.registerEvent(counting)
    app.setPollTime(50)
    app.bindKey('<space>', Timer.cycle)
    app.bindKey('1', Timer.cycle)
    return app
