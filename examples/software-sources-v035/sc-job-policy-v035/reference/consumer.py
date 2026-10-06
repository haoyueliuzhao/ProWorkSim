import policy


def review_jobs(jobs, queues, ceiling):
    accepted, rejected = [], []
    for index, job in enumerate(jobs):
        value = policy.validate_job(job, queues, ceiling)
        if value is None:
            rejected.append(index)
        else:
            accepted.append(value)
    return {"accepted": accepted, "rejected_indices": rejected}
