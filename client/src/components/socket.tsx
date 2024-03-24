"use client";
import {
    createContext,
    useEffect,
    useState,
    useRef,
    Dispatch,
    SetStateAction,
} from "react";

import crypto from "crypto";
interface ISocketContext {
    /**
     * if the socket is connected
     */
    ready: boolean;
    /**
     * what you are receiving
     */
    valueQueue: string[];
    /**
     * function to send data to the server
     * @param data
     * @returns
     */
    send: (data: string | ArrayBufferLike | Blob | ArrayBufferView) => void;
    setQueue: Dispatch<SetStateAction<string[]>>;
    phase: "lobby" | "input" | "waiting" | "song";
}

export const WebsocketContext = createContext<ISocketContext>({
    ready: false,
    valueQueue: [],
    send: () => {},
    setQueue: () => {},
    phase: "lobby",
});

export const WebsocketProvider = ({
    children,
}: {
    children: React.ReactNode;
}) => {
    const [isReady, setIsReady] = useState(false);
    const [valQueue, setValQueue] = useState<string[]>([]);
    const [client_id, setClientId] = useState("");

    const ws = useRef<WebSocket | null>(null);

    useEffect(() => {
        const id = crypto.randomUUID();
        setClientId(id);
        const socket = new WebSocket(`ws://localhost:8000/ws?client_id=${id}`);

        socket.onopen = () => setIsReady(true);
        socket.onclose = () => setIsReady(false);
        // socket.onmessage = (event) => setVal(event.data);
        socket.onmessage = (event) => {
            const eventObject = JSON.parse(event.data);
            // TODO: figure out what we sent
            if (eventObject.event === "audio") {
                // if this is audio data, add it to the audio queue
                setValQueue((prevValQueue) => {
                    return [...prevValQueue, eventObject["audio_data"]];
                });
            }
        };

        ws.current = socket;

        return () => {
            socket.close();
        };
    }, []);

    const ret: ISocketContext = {
        ready: isReady,
        valueQueue: valQueue,
        send: ws.current
            ? ws.current!.send.bind(ws.current)
            : () => {
                  console.error("cannot send because not connected");
                  return;
              },
        // send: ws.current
        //     ? () => {
        //           console.log("success:", ws.current);
        //       }
        //     : () => {
        //           console.error("cannot send because not connected");
        //           return;
        //       },
        setQueue: setValQueue,
        phase: "lobby",
    };

    return (
        <WebsocketContext.Provider value={ret}>
            {children}
        </WebsocketContext.Provider>
    );
};
