from app.functionality import andon, adjust_schedule, update_default, set_PCT, set_partsper
import os

raspi = os.sys.platform == 'linux'
title = 'Timer'
size = (800, 480)
bg = 'light grey'
font = 16
font_large = 'arial 60'
font_bold = 'arial 16 bold'
font_tCycle = 'arial 148'
font_consistency = 'arial 24 bold'


def layout(app):

    app.setFont(font)
    app.setTitle(title)
    app.setSize('fullscreen' if raspi else (800, 480))

    with app.tabbedFrame('Tabs'):

        with app.tab('Main'):
            app.setBg(bg)
            with app.frame('tCycle_frame', row=0, column=0):
                app.setFrameWidth('tCycle_frame', 5)
                app.addLabel('tCycle', row=0, column=0)
                app.setLabelSticky('tCycle', 'news')
                app.getLabelWidget('tCycle').config(font=font_tCycle)
            with app.frame('totals', row=1, column=0):
                app.addLabel('consistency', row=0, colspan=3)
                app.getLabelWidget('consistency').config(font=font_consistency)
                app.addLabel('early', row=1, column=0)
                app.addLabel('on_target', row=1, column=1)
                app.addLabel('late', row=1, column=2)
                for label in ['early', 'late', 'on_target']:
                    app.getLabelWidget(label).config(font=font_bold)
            with app.frame('Andons', row=0, column=1, rowspan=2):
                app.setFrameWidth('Andons', 2)
                app.addButton('Andon', andon)
                app.setButtonBg('Andon', '#AAAAAA')
                app.getButtonWidget('Andon').config(font=font_bold)
                app.setButtonHeight('Andon', 10)
                app.setButtonWidth('Andon', 1)
                app.addButton('Respond', andon)
                app.setButtonHeight('Respond', 1)
                app.setButtonWidth('Respond', 1)
                app.addLabel('andons', '')
                app.getLabelWidget('andons').config(font=font_bold)
        with app.tab('Setup'):
            app.setBg(bg)
            with app.labelFrame('Planned Cycle Time', row=0, column=0):
                app.setLabelFrameAnchor('Planned Cycle Time', 'n')
                app.getLabelFrameWidget('Planned Cycle Time').config(font=font_bold)
                app.setSticky('news')
                # app.addLabel('PCT_label', 'PCT', row=0, column=0)
                app.addLabel('PCT', row=0, column=0)
                app.getLabelWidget('PCT').config(font=font_large)
                # app.getLabelWidget('PCT_label').config(font='arial 72')
                with app.frame('PCT_entry', row=1, column=0):
                    app.setSticky('new')
                    app.addEntry('new_pct', colspan=3)
                    app.setEntryAlign('new_pct', 'center')
                    for button in range(1, 10):
                        name = '%s_PCT' % button
                        app.addButton(name, set_PCT, row=((button-1)//3)+1, column=(button + 2) % 3)
                        app.setButton(name, button)
                        app.setButtonWidth(name, 1)
                    col = 0
                    for button in ['Back', '0', 'OK']:
                        name = button + '_PCT'
                        app.addButton(name, set_PCT, row=4, column=col)
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
                    app.setSticky('new')
                    app.addEntry('new_partsper', colspan=3)
                    app.setEntryAlign('new_partsper', 'center')
                    for button in range(1, 10):
                        name = '%s_partsper' % button
                        app.addButton(name, set_partsper, row=((button-1)//3)+1, column=(button + 2) % 3)
                        app.setButton(name, button)
                        app.setButtonWidth(name, 1)
                    col = 0
                    for button in ['Back', '0', 'OK']:
                        name = button + '_partsper'
                        app.addButton(name, set_partsper, row=4, column=col)
                        col += 1
                        app.setButton(name, button)
                        app.setButtonWidth(name, 1)
        with app.tab('Schedule'):
            app.setBg(bg)
            for block in [1, 2, 3, 4]:
                with app.labelFrame('Block %s' % block, row=block//3, column=(block+1) % 2):
                    app.setSticky('new')
                    app.addButton('start%sDN' % block, adjust_schedule, 0, 0)
                    app.addLabel('start%s' % block, 'start', 0, 1)
                    app.addButton('start%sUP' % block, adjust_schedule, 0, 2)
                    app.addButton('end%sDN' % block, adjust_schedule, 1, 0)
                    app.addLabel('end%s' % block, 'end', 1, 1)
                    app.addButton('end%sUP' % block, adjust_schedule, 1, 2)
                    for label in ['start%s', 'end%s']:
                        app.getLabelWidget(label % block).config(font='arial 24 bold')
                    for button in ['start%sDN', 'start%sUP', 'end%sDN', 'end%sUP']:
                        app.setButton(button % block, '+5 min' if button[-1] == 'P' else '-5 min')
            app.addButton('Update Default', update_default, row=2, column=0, colspan=2)
    return app
