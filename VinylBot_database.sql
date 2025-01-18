CREATE TABLE IF NOT EXISTS Users (
userID BIGINT PRIMARY KEY,
username VARCHAR(255),
name VARCHAR(255) NOT NULL,
notif BOOLEAN NOT NULL,
UNIQUE (userID)
);

CREATE TABLE IF NOT EXISTS UserActions (
actionID SERIAL PRIMARY KEY,
userID BIGINT NOT NULL REFERENCES Users(userID),
actionType VARCHAR(255) NOT NULL,
actionDetails JSONB,
timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
UNIQUE (userID, actionType, actionDetails, timestamp)
);

CREATE TABLE IF NOT EXISTS Rating (
ratingID SERIAL PRIMARY KEY,
userValue INTEGER CHECK (userValue BETWEEN 1 AND 10) NOT NULL,
userID BIGINT NOT NULL REFERENCES Users(userID),
UNIQUE (ratingID, userValue, userID)
);

CREATE TABLE IF NOT EXISTS Label (
labelID SERIAL PRIMARY KEY,
labelName VARCHAR(255) NOT NULL,
labelCountry VARCHAR(255),
UNIQUE (labelName, labelCountry)
);

CREATE TABLE IF NOT EXISTS Artist (
artistID SERIAL PRIMARY KEY,
artistName VARCHAR(255) NOT NULL,
artistCountry VARCHAR(255),
UNIQUE (artistName)
);

CREATE TABLE IF NOT EXISTS Album (
albumID SERIAL PRIMARY KEY,
albumName VARCHAR(255) NOT NULL,
albumYear INTEGER CHECK (albumYear BETWEEN 1860 AND
EXTRACT(YEAR FROM CURRENT_DATE)),
genre VARCHAR(255),
artistID INTEGER NOT NULL REFERENCES Artist(artistID),
UNIQUE (albumName, albumYear, genre, artistID)
);

CREATE TABLE IF NOT EXISTS Record (
recordID SERIAL PRIMARY KEY,
recordSize VARCHAR(50) NOT NULL CHECK (recordSize IN ('LP', '12-inch single', '7-inch', '10-inch', 'EP', 'other')),
recordCond VARCHAR(50) CHECK (recordCond IN ('NEW', 'M', 'NM', 'VG+',
'VG', 'G+', 'G', 'P', 'B')),
recordYear INTEGER CHECK (recordYear BETWEEN 1948 AND
EXTRACT(YEAR FROM CURRENT_DATE)),
albumID INTEGER NOT NULL REFERENCES Album(albumID),
labelID INTEGER REFERENCES Label(labelID),
userID BIGINT NOT NULL REFERENCES Users(userID),
UNIQUE (recordSize, recordCond, recordYear, albumID, labelID, userID)
);





