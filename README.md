# ReadHub

## 1. Environment
1. the project run in `python=3.10` and you need to install the python dependence first
    ```shell
    pip install -r requirements.txt
    ```
2. set the API KEY for your chatGLM, you can set it by
    ```shell
    export API_KEY="<your_api_key>"     
    ```
3. Run the project by
    ```python
    python app.py
    ```

## 2. Settings
There is some settings you can change in the `constants.py`
1. `USE_CACHE`: set True to use the chatglm response cache in local file
2. `USE_DEFAULT_USER`: use it to disable the user system, so that you can use the project without login/register
