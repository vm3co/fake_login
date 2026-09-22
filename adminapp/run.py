import uvicorn

# 儲存logger
from backend.services.log_manager import Logger, timelog
logger = Logger(enable_console=True, enable_file=True).get_logger()

@timelog
def main():
    logger.debug('host="0.0.0.0", port=8080, reload=True')
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8080, reload=True)

if __name__ == "__main__":
    main()
