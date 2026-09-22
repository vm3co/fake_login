import { useRef, useEffect } from "react";

/**
 * Custom hook that provides an AbortController instance to be used
 * for aborting ongoing requests when a component using this hook is unmounted.
 *
 * It returns an object containing:
 * - `controllerRef`: A ref to the current AbortController instance.
 * - `createController`: A function to create a new AbortController instance,
 *   automatically aborting the previous one if it exists.
 *
 * The hook also ensures that any ongoing requests are aborted when the component
 * is unmounted or the page is closed or refreshed.
 */

export default function useAbortOnUnmount() {
    const controllerRef = useRef(null);

    // 建立新 controller 並自動存進 ref
    function createController() {
        if (controllerRef.current) controllerRef.current.abort();
        controllerRef.current = new AbortController();
        return controllerRef.current;
    }

    // 網頁關閉或是重整時自動 abort
    useEffect(() => {
        return () => {
            if (controllerRef.current) controllerRef.current.abort();
        };
    }, []);

    return { controllerRef, createController };
}

// 下面解釋在fetch時的用法
// const controller = createController();
// const res = await fetch("/api_url", {
//     method: "POST",
//     headers: { "Content-Type": "application/json" },
//     body: JSON.stringify({ orgs: orgsArr }),
//     signal: controller.signal,   // 設定 signal，用來中止(fetch abort) 這個 fetch 請求
// });