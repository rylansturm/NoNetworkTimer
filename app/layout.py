"""
The app is passed to the 'layout' function which creates all labels, buttons, tabs, etc.

Current app layout is:

Tabs:
    1.  Main
            the current cycle time, as well as live metrics and buttons for the andon system
    2.  Setup
            two keypads for adjusting the PCT and Partsper variables
    3.  Schedule
            shows the start/stop times for each block with buttons to adjust
    4.  Data
            password-protected entries for where data should be stored
"""


from app.functionality import Timer, PCT, Plan, Partsper, Andon, DB
import os

raspi = os.sys.platform == 'linux'      # boolean to prevent calling raspi specific functionality when testing
title = 'Timer'                         # app title - functionally arbitrary
size = (800, 480)                       # window size in pixels (ignored if raspi)
bg = 'light grey'                       # main background color
font = 16                               # universal font, unless specified below
font_large = 'arial 60'                 # |
font_bold = 'arial 16 bold'             # |
font_tCycle = 'arial 148'               # |
font_glance = 'arial 24 bold'           # |


def layout(app):
    """ a blank appJar.gui object is passed through this function to generate formatting, labels, buttons, etc. """

    app.setFont(font)
    app.setTitle(title)
    app.setSize('fullscreen' if raspi else (800, 480))

    """ 
    It's pretty easy to follow the layout of the app by following the indentation of the "with" statements 
    
    | this level has the separate windows (tabbedFrame and subWindow)
    |
        | this level has the separate tabs ("Main", "Setup", "Schedule" as documented above)
        |
            | this level and deeper has the labels, frames, buttons that rest in the frames
            |
    """

    with app.tabbedFrame('Tabs'):
        """ this is the frame the whole gui sits in """

        # Main Tab - Where the timer and metrics are visible
        with app.tab('Main'):
            app.setBg(bg)

            with app.frame('tCycle_frame', row=0, column=0):
                app.setFrameWidth('tCycle_frame', 5)
                app.addLabel('tCycle', row=0, column=0)
                app.setLabelSticky('tCycle', 'news')
                app.getLabelWidget('tCycle').config(font=font_tCycle)

            with app.frame('totals', row=1, column=0):

                with app.frame('glance', row=0, colspan=4):
                    column = 0
                    for label in ['ahead', 'current_time']:
                        app.addLabel(label, row=0, column=column)
                        app.getLabelWidget(label).config(font=font_glance)
                        app.setLabelRelief(label, 'ridge')
                        column += 1
                    app.setLabelSubmitFunction('ahead', PCT.catch_up)

                column = 0
                for label in ['early', 'late', 'on_target']:
                    app.addLabel(label, row=1, column=column)
                    app.setLabelRelief(label, 'ridge')
                    app.getLabelWidget(label).config(font=font_bold)
                    app.setLabelSubmitFunction(label, Timer.adjust_cycles)
                    column += 1
                app.addOptionBox('past_10', ['00:00:00'], row=1, column=3)

            with app.frame('Andons', row=0, column=1, rowspan=2):
                app.setFrameWidth('Andons', 2)
                app.addButton('Andon', Andon.andon)
                app.setButtonBg('Andon', '#AAAAAA')
                app.getButtonWidget('Andon').config(font=font_bold)
                app.setButtonHeight('Andon', 10)
                app.setButtonWidth('Andon', 1)
                app.addButton('Respond', Andon.andon)
                app.setButtonHeight('Respond', 1)
                app.setButtonWidth('Respond', 1)
                app.addLabel('andons', '')
                app.getLabelWidget('andons').config(font=font_bold)

        # Setup Tab - Where you set PCT and Parts per Cycle
        with app.tab('Setup'):
            app.setBg(bg)

            with app.labelFrame('Planned Cycle Time', row=0, column=0):
                app.setLabelFrameAnchor('Planned Cycle Time', 'n')
                app.getLabelFrameWidget('Planned Cycle Time').config(font=font_bold)
                app.setSticky('news')
                app.addLabel('PCT', row=0, column=0)
                app.getLabelWidget('PCT').config(font=font_large)

                with app.frame('PCT_entry', row=1, column=0):
                    app.setSticky('news')
                    app.addEntry('new_pct', colspan=3)
                    app.setEntryAlign('new_pct', 'center')
                    for button in range(1, 10):
                        name = '%s_PCT' % button
                        app.addButton(name, PCT.set_pct, row=((button - 1) // 3) + 1, column=(button + 2) % 3)
                        app.setButton(name, button)
                        app.setButtonWidth(name, 1)
                    col = 0
                    for button in ['Back', '0', 'OK']:
                        name = button + '_PCT'
                        app.addButton(name, PCT.set_pct, row=4, column=col)
                        col += 1
                        app.setButton(name, button)
                        app.setButtonWidth(name, 1)

            with app.labelFrame('Parts Per Cycle', row=0, column=1):
                app.setLabelFrameAnchor('Parts Per Cycle', 'n')
                app.getLabelFrameWidget('Parts Per Cycle').config(font=font_bold)
                app.setSticky('news')
                app.addLabel('partsper', row=0, column=0)
                app.getLabelWidget('partsper').config(font=font_large)

                with app.frame('partsper_entry', row=1, column=0):
                    app.setSticky('news')
                    app.addEntry('new_partsper', colspan=3)
                    app.setEntryAlign('new_partsper', 'center')
                    for button in range(1, 10):
                        name = '%s_partsper' % button
                        app.addButton(name, Partsper.set_partsper, row=((button-1)//3)+1, column=(button + 2) % 3)
                        app.setButton(name, button)
                        app.setButtonWidth(name, 1)
                    col = 0
                    for button in ['Back', '0', 'OK']:
                        name = button + '_partsper'
                        app.addButton(name, Partsper.set_partsper, row=4, column=col)
                        col += 1
                        app.setButton(name, button)
                        app.setButtonWidth(name, 1)

        # Schedule Tab - Where you adjust the schedule
        with app.tab('Schedule'):
            app.setBg(bg)

            for block in [1, 2, 3, 4]:
                with app.labelFrame('Block %s' % block, row=block//3, column=(block+1) % 2):
                    app.setSticky('new')
                    app.addButton('start%sDN' % block, Plan.adjust_schedule, 0, 0)
                    app.addLabel('start%s' % block, 'start', 0, 1)
                    app.addButton('start%sUP' % block, Plan.adjust_schedule, 0, 2)
                    app.addButton('end%sDN' % block, Plan.adjust_schedule, 1, 0)
                    app.addLabel('end%s' % block, 'end', 1, 1)
                    app.addButton('end%sUP' % block, Plan.adjust_schedule, 1, 2)
                    for label in ['start%s', 'end%s']:
                        app.getLabelWidget(label % block).config(font='arial 24 bold')
                    for button in ['start%sDN', 'start%sUP', 'end%sDN', 'end%sUP']:
                        app.setButton(button % block, '+5 min' if button[-1] == 'P' else '-5 min')
                    app.addLabel('block%sTime' % block, row=2, colspan=3)
            app.addLabel('availableTime', row=2, column=0, colspan=2)
            app.addButton('Update Default', Plan.update_default, row=3, column=0, colspan=2)
            app.addButton('Shut Down', Timer.shut_down)
            app.setButtonFg('Shut Down', 'red')
            app.setButtonBg('Shut Down', 'black')

        # Data Tab - Where db configurations are set
        with app.tab('Data'):
            app.setBg(bg)

            with app.frame('db_entries', row=0, column=0):
                app.setSticky('')
                app.addLabelOptionBox('db_type', ['local', 'server - api'])
                app.addLabelEntry('db_server')
                app.addLabelEntry('db_sequence')
                app.addLabelOptionBox('db_sequence_num', list(range(1, 10)))
                app.addButton('submit', DB.set_db)
                app.setOptionBox('db_type', DB.get_db()['type'])
                app.setEntry('db_server', DB.get_db()['server'] or '')
                app.setEntry('db_sequence', DB.get_db()['sequence'] or '')
                app.setOptionBox('db_sequence_num', DB.get_db()['sequence_num'] or '1')

            with app.frame('password', row=0, column=1):
                for button in range(1, 10):
                    name = '%s_password' % button
                    app.addButton(name, DB.enter_password, row=((button - 1) // 3) + 1, column=(button + 2) % 3)
                    app.setButton(name, button)
                    app.setButtonWidth(name, 1)
                col = 0
                for button in ['Back', '0', 'OK']:
                    name = button + '_password'
                    app.addButton(name, DB.enter_password, row=4, column=col)
                    col += 1
                    app.setButton(name, button)
                    app.setButtonWidth(name, 1)

    # Sub Windows are windows that pop up when certain events happen
    with app.subWindow('Catch Up?'):
        app.addLabel('catch_up_label', 'Cycle faster until you catch up to the plan?')
        app.addScale('catch_up_scale')
        app.addLabel('cycles_until_caught_up')
        app.showScaleValue('catch_up_scale', show=True)
        app.setScaleWidth('catch_up_scale', 35)
        app.addButtons(['OK', 'Cancel'], Timer.set_catch_up)

    app.addStatusbar(fields=3)

    return app
