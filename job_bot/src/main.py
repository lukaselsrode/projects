import yaml
from linkedin_api import Linkedin


JOB_TILTES= 'DevOps Engineer', 'Python Developer','Backend Engineer','Software Engineer'
def get_jobs(job_titles=JOB_TILTES):
    urls = []
    print("Getting Linkedin Api...")
    with open('../.secret.yaml', 'r') as file:
        secrets = yaml.safe_load(file)
    api = Linkedin(secrets['username'], secrets['password'])
    print("Getting Linkedin Jobs...")
    for title in job_titles:
        jobs = api.search_jobs(keywords=title,
                                experience=["2"],
                                job_type="F",
                                remote=["2"],
                                listed_at=86400
                            )
        for j in jobs:
            url = f"https://www.linkedin.com/jobs/search/?currentJobId={j['trackingUrn'].split(':')[-1]}"
            urls.append(url)
    urls = list(set(urls))
    print(f"Found {len(urls)} jobs for {len(job_titles)} job titles")
    return urls

def main():
    urls = get_jobs()
    print('Writing jobs to jobs.txt...')
    with open('../jobs.txt', 'w') as fp:
        for url in urls:
            fp.write("%s\n" % url)
    print('Done!')
    
if __name__ == '__main__':
    main()