-- Reference MySQL schema for the Hostel Recommender/Finder System.
-- This is generated automatically by SQLAlchemy (db.create_all() in load_data.py)
-- when DATABASE_URL points at MySQL - you do NOT need to run this file manually.
-- It is provided so the schema matches the proposal's "centralized MySQL database"
-- requirement and can be inspected/imported directly via phpMyAdmin if preferred.

CREATE DATABASE IF NOT EXISTS hostel_recommender
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE hostel_recommender;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'student',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hostels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    external_id VARCHAR(20) UNIQUE,
    name VARCHAR(150) NOT NULL,
    location VARCHAR(100) NOT NULL,
    district VARCHAR(50),
    hostel_type VARCHAR(20) DEFAULT 'mixed',
    room_type VARCHAR(20),
    price FLOAT NOT NULL,
    has_meals BOOLEAN DEFAULT FALSE,
    wifi BOOLEAN DEFAULT FALSE,
    laundry BOOLEAN DEFAULT FALSE,
    parking BOOLEAN DEFAULT FALSE,
    cctv BOOLEAN DEFAULT FALSE,
    security_guard BOOLEAN DEFAULT FALSE,
    study_room BOOLEAN DEFAULT FALSE,
    hot_water BOOLEAN DEFAULT FALSE,
    base_rating FLOAT,
    seed_review_count INT DEFAULT 0,
    distance_to_college_km FLOAT,
    distance_to_bus_stop_m FLOAT,
    occupancy INT,
    description TEXT,
    latitude FLOAT,
    longitude FLOAT,
    is_synthetic BOOLEAN DEFAULT TRUE,
    owner_id INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_location (location),
    INDEX idx_district (district),
    INDEX idx_latlon (latitude, longitude),
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hostel_id INT NOT NULL,
    user_id INT,
    reviewer_name VARCHAR(100),
    review_text TEXT NOT NULL,
    rating FLOAT,
    sentiment_score FLOAT,
    sentiment_label VARCHAR(10),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hostel_id) REFERENCES hostels(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS interactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    user_id INT,
    hostel_id INT NOT NULL,
    action VARCHAR(20) NOT NULL,
    query_text TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    FOREIGN KEY (hostel_id) REFERENCES hostels(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);
