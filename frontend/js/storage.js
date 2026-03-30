/**
 * FaceAuth — Client-Side Storage Manager
 * ========================================
 * Manages localStorage (preferences) and IndexedDB (cached data).
 */

const StorageManager = {
    // ── localStorage (Preferences) ───────────────────────────

    /**
     * Get a value from localStorage.
     */
    get(key) {
        try {
            const val = localStorage.getItem(`faceauth_${key}`);
            return val ? JSON.parse(val) : null;
        } catch {
            return null;
        }
    },

    /**
     * Set a value in localStorage.
     */
    set(key, value) {
        try {
            localStorage.setItem(`faceauth_${key}`, JSON.stringify(value));
        } catch (e) {
            console.warn('localStorage write failed:', e);
        }
    },

    /**
     * Remove a value from localStorage.
     */
    remove(key) {
        try {
            localStorage.removeItem(`faceauth_${key}`);
        } catch {
            // Ignore
        }
    },

    /**
     * Clear all FaceAuth localStorage entries.
     */
    clear() {
        try {
            const keys = [];
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && key.startsWith('faceauth_')) keys.push(key);
            }
            keys.forEach(k => localStorage.removeItem(k));
        } catch {
            // Ignore
        }
    },

    // ── IndexedDB (Cached Data) ──────────────────────────────

    _db: null,
    _dbName: 'FaceAuthDB',
    _dbVersion: 1,

    /**
     * Open IndexedDB connection.
     */
    async openDB() {
        if (this._db) return this._db;

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this._dbName, this._dbVersion);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // Store for cached session data
                if (!db.objectStoreNames.contains('sessions')) {
                    db.createObjectStore('sessions', { keyPath: 'id' });
                }

                // Store for offline login history
                if (!db.objectStoreNames.contains('loginCache')) {
                    const store = db.createObjectStore('loginCache', { keyPath: 'id', autoIncrement: true });
                    store.createIndex('timestamp', 'timestamp');
                }

                // Store for user preferences
                if (!db.objectStoreNames.contains('preferences')) {
                    db.createObjectStore('preferences', { keyPath: 'key' });
                }
            };

            request.onsuccess = (event) => {
                this._db = event.target.result;
                resolve(this._db);
            };

            request.onerror = (event) => {
                console.error('IndexedDB error:', event.target.error);
                reject(event.target.error);
            };
        });
    },

    /**
     * Store data in IndexedDB.
     */
    async idbPut(storeName, data) {
        try {
            const db = await this.openDB();
            const tx = db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            store.put(data);
            return new Promise((resolve, reject) => {
                tx.oncomplete = resolve;
                tx.onerror = () => reject(tx.error);
            });
        } catch (e) {
            console.warn('IndexedDB put failed:', e);
        }
    },

    /**
     * Get data from IndexedDB by key.
     */
    async idbGet(storeName, key) {
        try {
            const db = await this.openDB();
            const tx = db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.get(key);
            return new Promise((resolve, reject) => {
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
            });
        } catch (e) {
            console.warn('IndexedDB get failed:', e);
            return null;
        }
    },

    /**
     * Get all data from an IndexedDB store.
     */
    async idbGetAll(storeName) {
        try {
            const db = await this.openDB();
            const tx = db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.getAll();
            return new Promise((resolve, reject) => {
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
            });
        } catch (e) {
            console.warn('IndexedDB getAll failed:', e);
            return [];
        }
    },

    /**
     * Delete data from IndexedDB by key.
     */
    async idbDelete(storeName, key) {
        try {
            const db = await this.openDB();
            const tx = db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            store.delete(key);
            return new Promise((resolve, reject) => {
                tx.oncomplete = resolve;
                tx.onerror = () => reject(tx.error);
            });
        } catch (e) {
            console.warn('IndexedDB delete failed:', e);
        }
    },
};
