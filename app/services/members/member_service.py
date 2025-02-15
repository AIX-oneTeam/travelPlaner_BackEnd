from fastapi import Request


async def get_member_id_by_request(request: Request):
    try:
        if request.state.user is not None:
            member_id = request.state.user.get("member_id")
            return member_id
        else:
            return None
    except Exception as e:
        print("💡[ member_service ] get_member_id_by_request() 에러 : ", e)

