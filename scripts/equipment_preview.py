"""Isolated host/admin browser fixtures. Run with development test dependencies."""
import os
import runpy
os.environ.setdefault('AVAILABILITY_QA_PORT','18099')
os.environ['EQUIPMENT_QA_ADMIN']='1'
runpy.run_path(str(__import__('pathlib').Path(__file__).parent/'availability_preview.py'),run_name='__main__')
