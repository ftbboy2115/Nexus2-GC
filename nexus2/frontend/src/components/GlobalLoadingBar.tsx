import { createContext, useContext, useState, useCallback, useRef, useEffect, ReactNode } from 'react';

interface LoadingContextType {
    startLoading: () => void;
    stopLoading: () => void;
    isLoading: boolean;
}

const LoadingContext = createContext<LoadingContextType>({
    startLoading: () => { },
    stopLoading: () => { },
    isLoading: false,
});

export function LoadingProvider({ children }: { children: ReactNode }) {
    const [pendingRequests, setPendingRequests] = useState(0);
    const [showBar, setShowBar] = useState(false);
    const timerRef = useRef<NodeJS.Timeout | null>(null);

    const startLoading = useCallback(() => {
        setPendingRequests(prev => prev + 1);
    }, []);

    const stopLoading = useCallback(() => {
        setPendingRequests(prev => Math.max(0, prev - 1));
    }, []);

    // Show bar after 2 second delay when requests are pending
    useEffect(() => {
        if (pendingRequests > 0) {
            timerRef.current = setTimeout(() => {
                setShowBar(true);
            }, 2000);
        } else {
            if (timerRef.current) {
                clearTimeout(timerRef.current);
                timerRef.current = null;
            }
            setShowBar(false);
        }

        return () => {
            if (timerRef.current) {
                clearTimeout(timerRef.current);
            }
        };
    }, [pendingRequests]);

    return (
        <LoadingContext.Provider value={{ startLoading, stopLoading, isLoading: showBar }}>
            {showBar && <GlobalLoadingBar />}
            {children}
        </LoadingContext.Provider>
    );
}

export function useLoading() {
    return useContext(LoadingContext);
}

// The actual loading bar component
function GlobalLoadingBar() {
    return (
        <div className="global-loading-bar">
            <div className="global-loading-bar-progress"></div>
        </div>
    );
}

// Higher-order fetch wrapper that automatically tracks loading
export function useTrackedFetch() {
    const { startLoading, stopLoading } = useLoading();

    return useCallback(async (url: string, options?: RequestInit) => {
        startLoading();
        try {
            const response = await fetch(url, options);
            return response;
        } finally {
            stopLoading();
        }
    }, [startLoading, stopLoading]);
}
