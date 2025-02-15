USE easytravel;

-- 독립테이블

CREATE TABLE `administrative_division` (
	`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `city_province` VARCHAR(50) NOT NULL,
    `city_county` VARCHAR(50) NOT NULL
);

CREATE TABLE `member` (
    `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) NOT NULL,
    `email` VARCHAR(255) NOT NULL,
    `aceess_token` VARCHAR(255) NOT NULL,
    `refresh_token` VARCHAR(255) NOT NULL,
    `oauth` VARCHAR(255) NOT NULL,
    `nickname` VARCHAR(50) NULL,
    `sex` CHAR(10) NULL,
    `picture_url` VARCHAR(2083) NULL,
    `birth` DATE NULL,
    `address` VARCHAR(255) NULL,
    `zip` CHAR(10) NULL,
    `phone_number` VARCHAR(20) NULL,
    `voice` VARCHAR(255) NULL,
    `role` VARCHAR(10) NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE `plan` (
    `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `plan_name` VARCHAR(255) NULL,
    `start_date` DATETIME NULL,
    `end_date` DATETIME NULL,
    `main_location` VARCHAR(50) NULL,
    `ages` INT NULL,
    `companion_count` INT NULL,
    `plan_concepts` VARCHAR(255) NULL,
    `member_id` INT NOT null,
    CONSTRAINT `FK_plan_member` FOREIGN KEY (`member_id`) REFERENCES `member` (`id`)
); 


CREATE TABLE `spot_tag` (
    `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `spot_tag` VARCHAR(255) NOT NULL
);


-- 연결 테이블

CREATE TABLE `checklist` (
    `id`INT NOT NULL PRIMARY KEY,
    `plan_id` INT NOT NULL,
    `text` VARCHAR(255) NULL,
    `checked` BOOL NULL,
    CONSTRAINT `FK_checklist_plan_id` FOREIGN KEY (`plan_id`) REFERENCES `plan` (`id`)
);

CREATE TABLE `spot` (
    `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `kor_name` VARCHAR(255) NOT NULL,
    `eng_name` VARCHAR(255) NULL,
    `description` VARCHAR(255) NOT NULL,
    `address` VARCHAR(255) NOT NULL,
    `url` VARCHAR(2083) NULL,
    `image_url` VARCHAR(2083) NOT NULL,
    `map_url` VARCHAR(2083) NOT NULL,
    `latitude` Double NULL,
    `longitude` Double NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    `spot_category` INT NOT NULL,
    `phone_number` VARCHAR(300) NULL,
    `business_status` BOOL NULL,
    `business_hours` VARCHAR(255) NULL
);


-- 중간 테이블
CREATE TABLE `plan_spot_map` (
    `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `plan_id` INT NOT NULL,
    `spot_id` INT NOT NULL,
    `day_x` INT NOT NULL,
    `order` INT NOT NULL,
    `spot_time` TIME NULL,
    CONSTRAINT `FK_map_plan_id` FOREIGN KEY (`plan_id`) REFERENCES `plan` (`id`),
 	CONSTRAINT `FK_map_spot_id` FOREIGN KEY (`spot_id`) REFERENCES `spot` (`id`)
);

CREATE TABLE `plan_spot_tag_map` (
    `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `spot_id` INT NOT NULL,
    `spot_tag_id` INT NOT NULL,
    CONSTRAINT `FK_tag_map_spot_id` FOREIGN KEY (`spot_id`) REFERENCES `spot` (`id`),
  	CONSTRAINT `FK_tag_mpa_spot_tag_id` FOREIGN KEY (`spot_tag_id`) REFERENCES `spot_tag` (`id`)
);
