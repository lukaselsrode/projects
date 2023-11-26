from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.anchorlayout import AnchorLayout
from util import will_power, pos_reinforcement,neg_reinforcement,obsession, normalize_as_pct,store_measurement
from time import sleep
# View Layout
PAGE_LAYOUT = 1,3
# Question
QUESTION_FONT_SIZE = 40
QUESTION_SIZE_HINT_Y = 0.5 
# Buttons
BTN_FONT_SIZE = 30
BTN_SIZE_HINT=(0.5,0.25)   
SPACE_BTWEEN_BTNS = 50     
NO_COLOR,YES_COLOR = 'red','green'

class QuestionView(GridLayout):
    def __init__(self,app,**kwargs):
        super(QuestionView, self).__init__(**kwargs)
        self.app = app
        self.var = self.app.vars[self.app.var_index]
        self.question = self.var.questions[self.app.q_index]
        self.cols,self.rows= PAGE_LAYOUT # More rows for better distribution of space
        # Create an anchor layout for the exit button
        exit_button_layout = AnchorLayout(anchor_x='right', anchor_y='top', size_hint=(1, 0.1))
        exit_button = Button(text='Back', size_hint=(0.1, 1),background_color='red')
        exit_button.bind(on_release=self.exit_app)
        exit_button_layout.add_widget(exit_button)
        self.add_widget(exit_button_layout, index=0)
        # Adding a centered question
        self.question_label = Label(text=self.question, font_size=QUESTION_FONT_SIZE, halign='center', valign='middle', size_hint_y=QUESTION_SIZE_HINT_Y)
        self.question_label.bind(size=self.question_label.setter('text_size'))
        self.add_widget(self.question_label)
        # GridLayout for buttons
        self.button_layout = GridLayout(cols=2,spacing=SPACE_BTWEEN_BTNS, size_hint_y=0.5)
        self.button_layout.bind(minimum_height=self.button_layout.setter('height'))
        # NO button
        self.no_button = Button(text='No', font_size=BTN_FONT_SIZE, background_color=NO_COLOR,size_hint=BTN_SIZE_HINT)
        self.no_button.bind(on_release=self.on_no)
        self.button_layout.add_widget(self.no_button)
        # YES button
        self.yes_button = Button(text='Yes', font_size=BTN_FONT_SIZE, background_color=YES_COLOR,size_hint=BTN_SIZE_HINT)
        self.yes_button.bind(on_release=self.on_yes)
        self.button_layout.add_widget(self.yes_button)
        # Adding a wrapper layout to center the button layout
        wrapper_layout = GridLayout(cols=1, size_hint_y=1-QUESTION_SIZE_HINT_Y)
        wrapper_layout.add_widget(self.button_layout)
        self.add_widget(wrapper_layout)
 
        
    def on_yes(self, instance):
        print(f'YES on {self.question}')
        self.var.add_score(1)
        self.app.next_screen()

    def on_no(self, instance):
        print(f'NO on {self.question}')
        self.app.next_screen()
        
    def exit_app(self, instance):
        self.app.stop()

class VarMeasurer():
    def __init__(self,questions):
        self.questions,self.score=questions,0
        self.n = len(questions)
    
    def add_score(self,score):    
        self.score += score
    
    def norm_score(self):
        return normalize_as_pct(self.score/self.n,0,1)
    
class ProgramMeasurementApp(App):
    def __init__(self, **kwargs):
        super(ProgramMeasurementApp, self).__init__(**kwargs)
        
        self.wp = VarMeasurer(will_power())
        self.o = VarMeasurer(obsession())
        self.nr = VarMeasurer(neg_reinforcement())
        self.pr = VarMeasurer(pos_reinforcement())
        
        self.vars = [self.wp,self.nr,self.o,self.pr]
        self.q_index=self.var_index=0
        
    def clear_to_next_question(self):
        self.root.clear_widgets()
        sleep(0.2)
        self.root.add_widget(self.current_question_view())
        sleep(0.2)

    def current_question_view(self):
        return QuestionView(self)

    def next_var(self):    
        self.var_index += 1
        self.q_index=0
        
    def process_questions(self):
        wp,nr,o,pr=list(map(lambda x: x.norm_score(),self.vars))
        program=normalize_as_pct(wp+nr-(o-pr),-100,400)
        store_measurement([wp,nr,o,pr,program])

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
        self.stop()
        
    def build(self):
        return self.current_question_view()