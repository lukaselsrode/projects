from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from classes import TwoButtonLayout, ExitButton,BaseScreen
from util import MeasureCFG,normalize_as_pct,will_power,pos_reinforcement,neg_reinforcement,obsession,store_measurement

PAGE_LAYOUT = MeasureCFG["layout"]
QUESTION = MeasureCFG["question"]


class QuestionView(GridLayout):
    def __init__(self, app, **kwargs):
        super(QuestionView, self).__init__(**kwargs)
        self.app = app
        self.var = self.app.vars[self.app.var_index]
        self.question = self.var.questions[self.app.q_index]
        self.cols, self.rows = PAGE_LAYOUT

        self.exit = ExitButton(self.app)
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
        self.app.next_screen()

    def on_no(self, instance):
        self.app.next_screen()


class VarMeasurer:
    def __init__(self, questions):
        self.questions, self.score = questions, 0
        self.n = len(questions)

    def add_score(self, score):
        self.score += score

    def norm_score(self):
        return normalize_as_pct(self.score / self.n, 0, 1)


class ProgramMeasurementScreen(BaseScreen):
    def __init__(self, **kwargs):
        super(ProgramMeasurementScreen, self).__init__(**kwargs)

        self.wp = VarMeasurer(will_power())
        self.o = VarMeasurer(obsession())
        self.nr = VarMeasurer(neg_reinforcement())
        self.pr = VarMeasurer(pos_reinforcement())

        self.vars = [self.wp, self.nr, self.o, self.pr]
        self.q_index = self.var_index = 0

    def clear_to_next_question(self):
        self.root.clear_widgets()
        self.root.add_widget(self.current_question_view())

    def current_question_view(self):
        return QuestionView(self)

    def next_var(self):
        self.var_index += 1
        self.q_index = 0

    def process_questions(self):
        wp, nr, o, pr = list(map(lambda x: x.norm_score(), self.vars))
        program = normalize_as_pct(wp + nr - (o - pr), -100, 400)
        store_measurement([wp, nr, o, pr, program])

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
        self.close()

    def build(self):
        return self.current_question_view()
