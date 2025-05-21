import { useState } from "react";

const CreateUrl = () => {
  const [selectedOption, setSelectedOption] = useState("");
  const [outputText, setOutputText] = useState("");

  const handleConfirm = () => {
    const url_head = "http://localhost:8090/qrcode/";
    const url_end = "/uuid?uuid=99999_99999";
    if (!selectedOption) {
      alert("請先選擇一個選項");
    } else {
      setOutputText(url_head + selectedOption + url_end);
    }
  };

  const handleCopy = async () => {
    if (!outputText) {
      alert("沒有可以複製的內容！");
      return;
    }
    try {
      await navigator.clipboard.writeText(outputText);
      alert("複製成功！");
    } catch (err) {
      alert("複製失敗：" + err.message);
    }
  };

  return (
    <div className="container">
      <h4 className="mb-3">請選擇登入頁面版型：</h4>

      <div className="form-check mb-2">
        <input
          className="form-check-input"
          type="radio"
          name="option"
          id="test"
          value="test"
          onChange={(e) => setSelectedOption(e.target.value)}
        />
        <label className="form-check-label" htmlFor="test">
          test
        </label>
      </div>

      <div className="form-check mb-3">
        <input
          className="form-check-input"
          type="radio"
          name="option"
          id="googledrive"
          value="googledrive"
          onChange={(e) => setSelectedOption(e.target.value)}
        />
        <label className="form-check-label" htmlFor="googledrive">
          Google Drive
        </label>
      </div>

      <div className="mb-3">
        <button className="btn btn-primary me-2" onClick={handleConfirm}>
          產生網址
        </button>
        <button className="btn btn-secondary" onClick={handleCopy}>
          複製結果
        </button>
      </div>

      {outputText && (
        <div className="alert alert-info" role="alert">
          {outputText}
        </div>
      )}
    </div>
  );
};

export default CreateUrl;
