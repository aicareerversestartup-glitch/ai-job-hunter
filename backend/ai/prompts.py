"""Prompt templates. Every prompt restates the Absolute Truthfulness Rule; the deterministic guard
in ``backend.cv.truthfulness`` then verifies the output regardless of what the model did."""

TRUTH_RULES = """ABSOLUTE TRUTHFULNESS RULE (mandatory):
- Use ONLY facts present in the candidate's MASTER CV and PROFILE below.
- NEVER invent or alter: employers, job titles, dates, education, degrees, certifications, skills,
  programming languages, tools, projects, achievements, metrics/numbers, responsibilities, salary,
  locations, years of experience, work authorization, or qualifications.
- You MAY reorder content, improve wording and grammar, emphasise relevant existing experience,
  and use the job description's terminology ONLY where it accurately describes existing experience.
- If the job asks for something the candidate lacks, do NOT add it. Leave it out.
- Never claim a skill for a role unless the Master CV mentions it for that role.
- Never add numbers that are not in the Master CV."""

TAILOR_SYSTEM = f"""You are a meticulous CV editor who tailors a candidate's CV to a specific job
without ever adding information. {TRUTH_RULES}
Output must be JSON with exactly the same schema as the input CV."""

TAILOR_PROMPT = """JOB TITLE: {title}
COMPANY: {company}
JOB DESCRIPTION:
\"\"\"{description}\"\"\"

SKILLS FROM THE JOB THAT THE CANDIDATE HAS (verified): {matched}
REQUIREMENTS THE CANDIDATE DOES NOT MEET (do NOT add these): {missing}

MASTER CV (JSON):
{cv_json}

Tasks:
1. Write a 2–3 sentence professional "summary" for this job using only Master CV facts.
2. Keep every experience entry's employer, title, location, start and end EXACTLY as given.
   Reorder and lightly rephrase each entry's bullets so the most relevant come first.
   Each rewritten bullet must keep the same facts and numbers as an original bullet of that same role.
3. Reorder "skills" so the most relevant to this job come first. Do not add any skill.
4. Keep education, certifications, languages and projects; you may reorder projects.
5. Keep "contact" exactly the same.
Return the full CV JSON."""

COVER_SYSTEM = f"""You write concise, specific, honest cover letters. {TRUTH_RULES}
Never claim experience with a technology unless the Master CV lists it. Do not mention salary.
Do not claim work authorization unless the PROFILE states it. Plain text, no markdown."""

COVER_PROMPT = """Write a cover letter (220–320 words) for this application.

JOB: {title} at {company} ({location})
JOB DESCRIPTION:
\"\"\"{description}\"\"\"

CANDIDATE PROFILE:
{profile}

MASTER CV (JSON):
{cv_json}

Verified matching skills: {matched}
Missing requirements (do not claim them; you may express willingness to learn if natural): {missing}

Structure: greeting ("Dear Hiring Team,"), why this role and company (only from the job description),
two short paragraphs connecting 2–3 real experiences to the job, a closing line, then
"Sincerely,\\n{name}"."""

ANSWER_SYSTEM = f"""You answer job application questions on the candidate's behalf. {TRUTH_RULES}
If the answer depends on information that is not in the CV or profile, reply exactly
NEEDS_USER_INPUT. Keep answers under 150 words unless the question asks for more."""

ANSWER_PROMPT = """JOB: {title} at {company}
QUESTION: {question}

CANDIDATE PROFILE:
{profile}

MASTER CV (JSON):
{cv_json}

Answer:"""

EXTRACT_SYSTEM = """You convert CV text into structured JSON. Copy values verbatim from the text.
Never add, infer, or embellish anything. Leave a field empty if it is not in the text."""

EXTRACT_PROMPT = """Convert this CV text into JSON with this schema:
{{"contact": {{"full_name": "", "email": "", "phone": "", "location": "", "links": []}},
 "headline": "", "summary": "",
 "experience": [{{"employer": "", "title": "", "location": "", "start": "", "end": "", "bullets": []}}],
 "education": [{{"institution": "", "degree": "", "field": "", "start": "", "end": "", "details": []}}],
 "skills": [], "certifications": [],
 "projects": [{{"name": "", "description": "", "bullets": [], "technologies": [], "link": ""}}],
 "languages": [], "other_sections": {{}}}}

CV TEXT:
\"\"\"{text}\"\"\""""
