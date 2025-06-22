I changed the folder names to sentiment_analysis and profanity_check. Then I also changed the imports in the setup file.


# log to run the tests #

(.venv) PS C:\Users\hanna\OneDrive\Uni\4. Semester\dic\DIC-Assignment-3> pytest tests
============================================================================== test session starts ===============================================================================
platform win32 -- Python 3.11.6, pytest-8.3.5, pluggy-1.6.0
rootdir: C:\Users\hanna\OneDrive\Uni\4. Semester\dic\DIC-Assignment-3
collected 8 items                                                                                                                                                                 

tests\test_preprocess_lambda.py ..                                                                                                                                                                                    [ 25%]
tests\test_profanity_lambda.py ...                                                                                                                                                                                    [ 62%]
tests\test_sentiment_lambda.py ...                                                                                                                                                                                    [100%]

==================================================================================================== 8 passed in 13.18s ====================================================================================================
(.venv) PS C:\Users\hanna\OneDrive\Uni\4. Semester\dic\DIC-Assignment-3>