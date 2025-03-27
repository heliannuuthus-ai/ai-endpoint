def unambiguous(**kwargs):
    return {k: v for k, v in kwargs.items() if v is not None}


def pagination(page: int, per_page: int):
    return {"page": page, "per_page": per_page}
