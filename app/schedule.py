import datetime
import configparser


class Schedule:
    def __init__(self, now=None):
        conf = configparser.ConfigParser()
        conf.read('schedules.ini')
        if not now:
            now = datetime.datetime.now()
        self.shift = self.shift_select(now)
        starts = conf[self.shift]['start'].split(', ')
        ends = conf[self.shift]['end'].split(', ')
        self.start = []
        self.end = []
        for start in starts:
            start = datetime.datetime.time(datetime.datetime.strptime(start, '%H%M'))
            self.start.append(Schedule.combine(now, start))
        for end in ends:
            end = datetime.datetime.time(datetime.datetime.strptime(end, '%H%M'))
            self.end.append(Schedule.combine(now, end))
        self.start.sort()
        self.end.sort()

    def schedule(self):
        schedule = self.start + self.end
        schedule.sort()
        return schedule

    def get_block(self):
        block = 0
        for time in self.start:
            if datetime.datetime.now() > time:
                block += 1
        if not block:
            block = 1
        return block

    def block_time(self):
        block = self.get_block()
        start = self.start[block-1]
        end = self.end[block-1]
        return (end - start).total_seconds()

    def available_time(self):
        available = 0
        for time in range(4):
            available += (self.end[time] - self.start[time]).total_seconds()
        return int(available)

    def kpi_date(self):
        return datetime.datetime.date(self.start[0])

    @staticmethod
    def shift_select(now=None):
        """ Returns the shift name {str} wherein lies the given time (now arg).
            If no time is provided, the current timestamp will be used. """
        if not now:
            now = datetime.datetime.now()
        if now.hour < 7:
            return 'Grave'
        elif now.hour < 15:
            return 'Day'
        elif now.hour < 23:
            return 'Swing'
        else:
            return 'Grave'

    @staticmethod
    def combine(now, time):
        """ Returns a datetime object that falls within the current shift.
            This allows Schedule objects to be created before or after midnight for Grave. """
        date = datetime.datetime.today()
        if now.hour >= 23:
            if time.hour <= 7:
                date += datetime.timedelta(days=1)
        elif now.hour < 7:
            if time.hour >= 23:
                date -= datetime.timedelta(days=1)
        return datetime.datetime.combine(date, time)
