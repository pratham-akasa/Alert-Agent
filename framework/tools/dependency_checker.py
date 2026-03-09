"""
Tool: Dependency Checker

Reads the service_dependencies_kb.md file to find dependencies for services.
"""

import os
from langchain_core.tools import tool

@tool
def check_service_dependencies() -> str:
    """
    Read the service_dependencies_kb.md file to find dependencies for a service.
    
    Use this tool to find out what other services might be affected or causing issues
    when a primary service alarm goes off.
    
    Returns:
        The full markdown text of the service dependencies knowledge base.
    """
    file_path = os.path.join(os.path.dirname(__file__), "service_dependencies_kb.md")
    if not os.path.exists(file_path):
        return "Dependencies KB file not found at " + file_path
        
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()
