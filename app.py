from flask import Flask, render_template, request, session, redirect, url_for
from flask import render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
import re
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import openai  # don't go for upgraded version
import json
import requests
from flask_weasyprint import HTML, render_pdf
from weasyprint import CSS
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'alpha-beta-gamma'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
openai.api_key = os.getenv("api_key")


# Create a Markdown instance with the FencedCodeExtension
md = markdown.Markdown(extensions=[FencedCodeExtension()])



class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)




class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique = True)
    email = db.Column(db.String(50), unique = True)
    password = db.Column(db.String(80))
    courses = db.relationship('Course', backref='user', lazy=True)
    date_joined = db.Column(db.DateTime, default=datetime.now)




@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))




@app.route("/quiz_interface")
def quiz_interface():
    return render_template("home.html")





@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    if (request.method == "POST"):
        print(request.form)
        language = request.form["language"]
        questions = request.form["ques"]
        choices = request.form["choices"]
        #difficulty = request.form["diff"]

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": f"Hey chat gpt prepare a quick quiz on this programming language: {language} and prepare {questions} number of questions and for each of them keep {choices} number of choices, reply in the form of an object, make sure the response object contains topic, questions array containing question, choices and it's answer,print them in json format"
                }
            ],  
            temperature=0.7,
        )
        print(response['choices'][0]['message']['content'])
        quiz_content = response['choices'][0]['message']['content']
        #print(quiz_content)
        

        # Convert the content string to a dictionary
        quiz_content = json.loads(quiz_content)
        
        # In your code, session is likely a Flask session object.
        # Flask provides a session object as a dictionary that you can use to store values that are "remembered" between requests.In this example, session['key'] = 'value' stores a value in the session that can be accessed in subsequent requests.
        # In your code, session['response'] = response is storing the response dictionary in the session so it can be accessed later, perhaps in a different route or request.
        session['response'] = quiz_content
        # app.secret_key = os.environ.get("SECRET_KEY")

        return render_template("quiz.html", quiz_content=quiz_content)
    
    if request.method == "GET":
        score = 0
        actual_answers = []
        given_answers = list(request.args.values()) or []
        res = session.get('response', None)
        for answer in res["questions"]:
            actual_answers.append(answer["answer"])
        if (len(given_answers)!= 0):
            for i in range(len(actual_answers)):
                if actual_answers[i] == given_answers[i]:
                    score=score+1
        return render_template("score.html", actual_answers=actual_answers, given_answers=given_answers, score=score)





@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        hashed_password = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        new_user = User(username=request.form['username'], email=request.form['email'], password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')




@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('login.html')




@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))




@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_authenticated:
        return render_template('dashboard.html', user=current_user)
    else:
        return redirect(url_for('login'))





@app.route('/')
def home():
    if current_user.is_authenticated:
        saved_courses = Course.query.filter_by(user_id=current_user.id).all()
        recommended_courses = generate_recommendations(saved_courses)
        return render_template('app.html', saved_courses=saved_courses, recommended_courses = recommended_courses, user=current_user)
    else:
        return redirect(url_for('login'))




@app.route('/course', methods=['GET', 'POST'])
@login_required
def course():
    if request.method == 'POST':
        course_name = request.form['course_name']
        completions = generate_text(course_name)
        print(f"course_name: {course_name}")
        rendered = render_template('courses/course1.html', completions=completions, course_name=course_name)
        new_course = Course(course_name=course_name, content=rendered, user_id=current_user.id)
        db.session.add(new_course)
        db.session.commit()
        return rendered
    return render_template('courses/course1.html')




@app.route('/r_course/<course_name>', methods=['GET', 'POST'])
@login_required
def r_course(course_name):
    completions = None  # Initialize completions to None
    if request.method == 'POST':
        completions = generate_text(course_name)
        print(f"course_name: {course_name}")
        rendered = render_template('courses/course1.html', completions=completions, course_name=course_name)
        new_course = Course(course_name=course_name, content=rendered, user_id=current_user.id)
        db.session.add(new_course)
        db.session.commit()
        return rendered
    # If the request method is 'GET', generate the text for the course
    completions = generate_text(course_name)
    return render_template('courses/course1.html', completions=completions, course_name=course_name)


@app.route('/saved_course/<course_name>')
@login_required
def saved_course(course_name):
    course = Course.query.filter_by(course_name=course_name, user_id=current_user.id).first()
    if course is None:
        # If there is no course with the given name, redirect to the home page
        return "<p>Course not found</p>"
    else:
        # If a course with the given name exists, render a template and pass the course to it
        return render_template('courses/saved_course.html', course=course)




@app.route('/module/<course_name>/<module_name>', methods=['GET'])
def module(course_name,module_name):
    content = generate_module_content(course_name,module_name)
    if not content:
        return "<p>Module not found</p>"
    html = render_template('module.html', content=content)
    
    # If the 'download' query parameter is present in the URL, return the page as a PDF
    if 'download' in request.args:
        #Create a CSS object for the A3 page size
        a3_css = CSS(string='@page {size: A3; margin: 1cm;}')
        return render_pdf(HTML(string=html), stylesheets=[a3_css])

    # Otherwise, return the page as HTML
    return html 


@app.route('/app1')
def app1():
    if current_user.is_authenticated:
        saved_courses = Course.query.filter_by(user_id=current_user.id).all()
        recommended_courses = generate_recommendations(saved_courses)
        return render_template('app.html', saved_courses=saved_courses, recommended_courses = recommended_courses, user=current_user)
    else:
        return redirect(url_for('login'))





def markdown_to_list(markdown_string):
    # Split the string into lines
    lines = markdown_string.split('\n')
    # Use a regular expression to match lines that start with '* '
    list_items = [re.sub(r'\* ', '', line) for line in lines if line.startswith('* ')]
    return list_items




def generate_text(course):
    prompts = {
        'approach': f"You are a pedagogy expert and you are designing a learning material for {course} for an undergraduate university student. Your task is to create a structured and technical approach to studying this material, along with clear learning outcomes. Additionally, provide reference links (YouTube videos, articles, etc.), study material links, and reference books to supplement the learning process.",
        'modules': f"Based on the course {course}, please provide a list of modules that you would include in the course. Each module should be a subtopic of the course and should be listed in bullet points. Additionally, please provide a brief description of each module to give an overview of the content covered in the module.",
        'resources': f"Based on the course {course}, please provide a list of external resources such as YouTube video links, Wikipedia articles, and other relevant websites that would be beneficial for students to deepen their understanding of the course material. Include a brief description of each resource, especially focusing on YouTube links."
    }
    completions = {}
    
    for key, prompt in prompts.items():
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=3000,  # Increase tokens for more detailed responses
        )
        result = response['choices'][0]['message']['content']
        
        if key == 'modules':
            # Replace bullet points with asterisks
            markdown_string = result.replace('•', '*') if result else ""
            completions[key] = markdown_to_list(markdown_string) if markdown_string else []
        elif key == 'resources':
            # Convert the resources into a list of dictionaries with descriptions
            resources_list = []
            for line in result.split('\n'):
                if line.strip():
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        resource_type = parts[0].strip()
                        resource_description = parts[1].strip()
                        resources_list.append({'type': resource_type, 'description': resource_description})
            completions[key] = resources_list
        else:
            completions[key] = markdown.markdown(result) if result else ""
    
    return completions




def generate_module_content(course_name, module_name):
    # First prompt for module content
    module_prompt = f"Course Name: {course_name} Topic: {module_name}. Please provide a comprehensive explanation of {module_name}. Feel free to use examples or analogies to clarify complex ideas. Additionally, if there are specific aspects or questions you'd like to address within the topic, please mention them for a more focused response. Also, provide relevant YouTube links for further study."
    
    module_response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": module_prompt}
        ],
        temperature=0.1,
        max_tokens=5000,
    )
    module_content = module_response['choices'][0]['message']['content'] if module_response['choices'][0]['message']['content'] else ""

    # Second prompt for code snippets
    code_prompt = f"Course Name: {course_name} Topic: {module_name}. If the explanation of {module_name} requires code snippets for better understanding, please provide the relevant code snippets."
    
    code_response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": code_prompt}
        ],
        temperature=0.1,
        max_tokens=5000,
    )
    code_content = code_response['choices'][0]['message']['content'] if code_response['choices'][0]['message']['content'] else ""

    # Third prompt for ASCII art
    ascii_prompt = f"Course Name: {course_name} Topic: {module_name}. If the explanation of {module_name} requires diagram snippets for better understanding, please provide the relevant diagram snippets in the form of ASCII art."
    
    ascii_response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": ascii_prompt}
        ],
        temperature=0.1,
        max_tokens=5000,
    )
    ascii_content = ascii_response['choices'][0]['message']['content'] if ascii_response['choices'][0]['message']['content'] else ""

    # Convert the markdown string to HTML, wrapping code snippets with <pre><code> tags
    module_content_html = md.convert(module_content)
    code_content_html = md.convert(code_content)
    ascii_content_html = md.convert(ascii_content)

    # Combine the module content and code snippets
    combined_content = f"{module_content_html}\n{code_content_html}\n{ascii_content_html}"

    return combined_content




def generate_recommendations(saved_courses):
    recommended_courses = []
    
    for course in saved_courses:
        prompt = f"Based on the course {course.course_name}, please provide just a single course name at the top and a description for new recommended course that would be beneficial for the student to take next. The description should be concise and informative (less than 70 characters)."
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=70,
        )
        result = response['choices'][0]['message']['content']
        
        if result:
            course_name = result.strip()
            course_description = markdown.markdown(course_name)
            recommended_courses.append({'name': course_name, 'description': course_description})
    
    return recommended_courses


@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="127.0.0.1", debug=True)
