"""
Database Schemas for LeetCode-style app

Each Pydantic model corresponds to a MongoDB collection with the lowercase
class name used as the collection name.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr


class User(BaseModel):
    email: EmailStr
    name: str = Field(..., description="Full name")
    password_hash: str
    is_admin: bool = False


class TestCase(BaseModel):
    input: str
    output: str
    hidden: bool = False


class Problem(BaseModel):
    title: str
    description: str
    difficulty: str = Field(..., pattern=r"^(Easy|Medium|Hard)$")
    starter_code: Optional[str] = ""
    test_cases: List[TestCase] = []


class Submission(BaseModel):
    user_id: str
    problem_id: str
    language: str = Field(..., pattern=r"^(javascript|python)$")
    code: str
    status: str = Field("Pending", pattern=r"^(Pending|Accepted|Wrong Answer|Error)$")
    stdout: Optional[str] = ""
    stderr: Optional[str] = ""
