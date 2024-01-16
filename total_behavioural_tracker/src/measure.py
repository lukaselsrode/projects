from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from classes import TwoButtonLayout, ExitButton, BaseScreen
from util import (
    get_app_cfg,
    normalize_as_pct,
    will_power,
    pos_reinforcement,
    neg_reinforcement,
    obsession,
    update_reccords,
)
MeasureCFG = get_app_cfg('measure')
PAGE_LAYOUT = MeasureCFG["layout"]
QUESTION = MeasureCFG["question"]


class QuestionView(GridLayout):
    def __init__(self, measurer, app, **kwargs):
        super(QuestionView, self).__init__(**kwargs)
        self.measurer = measurer
        self.app = app
        self.var = self.measurer.vars[self.measurer.var_index]
        self.cols, self.rows = PAGE_LAYOUT
        # Catch non-configed files, on fresh app
        self.question = (
            self.var.questions[self.measurer.q_index]
            if self.var.questions
            else "NO QUESTION"
        )
        self.exit = ExitButton(application=self.app)
        self.add_widget(self.exit.layout, index=0)

        self.question_label = Label(
            text=self.question,
            font_size=QUESTION["font_size"],
            halign="center",
            valign="middle",
            size_hint_y=QUESTION["size_y"],
            color="yellow",
            italic=True,
        )
        self.question_label.bind(size=self.question_label.setter("text_size"))
        self.add_widget(self.question_label)

        self.buttons_layout = TwoButtonLayout(
            rtxt="YES", rfunc=self.on_yes, ltxt="NO", lfunc=self.on_no
        )
        self.add_widget(self.buttons_layout)

    def on_yes(self, instance):
        self.var.add_score(1)
        self.measurer.next_screen()

    def on_no(self, instance):
        self.measurer.next_screen()


class VarMeasurer:
    def __init__(self, questions):
        self.questions, self.score = questions, 0
        self.n = len(questions)

    def add_score(self, score):
        self.score += score

    def norm_score(self):
        return normalize_as_pct(self.score / self.n, 0, 1)


class ProgramMeasurementScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super(ProgramMeasurementScreen, self).__init__(**kwargs)
        self.app = app
        self.wp = VarMeasurer(will_power())
        self.o = VarMeasurer(obsession())
        self.nr = VarMeasurer(neg_reinforcement())
        self.pr = VarMeasurer(pos_reinforcement())

        self.vars = [self.wp, self.nr, self.o, self.pr]
        self.q_index = self.var_index = 0
        self.add_widget(self.current_question_view())

    def clear_to_next_question(self):
        self.clear_widgets()
        self.add_widget(self.current_question_view())

    def current_question_view(self):
        return QuestionView(measurer=self, app=self.app)

    def next_var(self):
        self.var_index += 1
        self.q_index = 0

    def process_questions(self):
        wp, nr, o, pr = list(map(lambda x: x.norm_score(), self.vars))
        program = normalize_as_pct(wp + nr - (o - pr), -100, 400)
        update_reccords([wp, nr, o, pr, program])

    def next_screen(self):
        self.q_index += 1
        if self.q_index < self.vars[self.var_index].n:
            self.clear_to_next_question()
            return
        self.next_var()
        if self.var_index < len(self.vars):
            self.clear_to_next_question()
            return
        self.process_questions()
        self.app.switch_screen("main")
